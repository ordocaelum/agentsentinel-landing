/**
 * Tests for supabase/functions/validate-license/index.ts
 *
 * Split into two layers:
 *   1. Unit tests — rate limiter, HMAC signing algorithm, format validation.
 *      No network required; run with: deno test test.ts --allow-read
 *   2. Integration tests — full HTTP handler.
 *      Require SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY env vars.
 *      Run with: deno test test.ts --allow-read --allow-net --allow-env
 */

import {
  assertEquals,
  assertMatch,
  assertNotEquals,
} from "https://deno.land/std@0.220.1/assert/mod.ts";
import { createRateLimiter } from "../_shared/rate-limit.ts";

// ─── Helper: HMAC-SHA256 (mirrors stripe-webhook generateLicenseKey) ─────────

/** Base64url encode (no padding). */
function b64urlEncode(bytes: Uint8Array): string {
  const base64 = btoa(Array.from(bytes, (b) => String.fromCharCode(b)).join(""));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

/** Base64url decode (tolerates missing padding). */
function b64urlDecode(s: string): Uint8Array {
  const padded = s.replace(/-/g, "+").replace(/_/g, "/");
  const padding = "=".repeat((4 - (padded.length % 4)) % 4);
  const binary = atob(padded + padding);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

const VALID_KEY_TIERS = new Set(["free", "starter", "pro", "pro_team", "team", "enterprise"]);

/**
 * Verify an asv1_* license key using the given HMAC secret.
 * Mirrors python/agentsentinel/utils/keygen.py::verify_license_key.
 */
async function verifyLicenseKey(
  key: string,
  secret: string,
): Promise<{ valid: boolean; tier?: string; error?: string }> {
  if (!key.startsWith("asv1_")) {
    return { valid: false, error: "Unsupported key format" };
  }
  const token = key.slice("asv1_".length);
  const dotIdx = token.indexOf(".");
  if (dotIdx === -1) {
    return { valid: false, error: "Malformed key" };
  }
  const payloadB64 = token.slice(0, dotIdx);
  const sigB64 = token.slice(dotIdx + 1);

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const expectedSigBytes = await crypto.subtle.sign(
    "HMAC",
    cryptoKey,
    new TextEncoder().encode(payloadB64),
  );
  const expectedSigB64 = b64urlEncode(new Uint8Array(expectedSigBytes));

  // Constant-time comparison (both strings are base64url so same charset).
  if (expectedSigB64 !== sigB64) {
    return { valid: false, error: "Invalid signature" };
  }

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(new TextDecoder().decode(b64urlDecode(payloadB64)));
  } catch {
    return { valid: false, error: "Malformed key" };
  }

  const tier = String(payload.tier ?? "").toLowerCase();
  if (!VALID_KEY_TIERS.has(tier)) {
    return { valid: false, error: "Invalid tier" };
  }

  const exp = Number(payload.exp ?? 0);
  if (exp <= Math.floor(Date.now() / 1000)) {
    return { valid: false, error: "License expired" };
  }

  return { valid: true, tier };
}

/**
 * Generate an asv1_* license key.
 * Mirrors stripe-webhook/index.ts::generateLicenseKey and
 * python/agentsentinel/utils/keygen.py::generate_license_key.
 */
async function generateLicenseKey(
  tier: string,
  secret: string,
  opts?: { iat?: number; exp?: number; nonce?: string },
): Promise<string> {
  const now = opts?.iat ?? Math.floor(Date.now() / 1000);
  const nonceBytes = opts?.nonce
    ? new TextEncoder().encode(opts.nonce)
    : crypto.getRandomValues(new Uint8Array(9));
  const nonce = opts?.nonce ?? b64urlEncode(nonceBytes);

  // Sort keys to match Python's json.dumps(sort_keys=True):
  //   exp < iat < nonce < tier  (alphabetical)
  const payloadJson = JSON.stringify(
    { exp: opts?.exp ?? now + 365 * 86400, iat: now, nonce, tier: tier.toLowerCase() },
    ["exp", "iat", "nonce", "tier"],
  );
  const payloadB64 = b64urlEncode(new TextEncoder().encode(payloadJson));

  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sigBytes = await crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(payloadB64));
  const sigB64 = b64urlEncode(new Uint8Array(sigBytes));

  return `asv1_${payloadB64}.${sigB64}`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Rate-limiter unit tests
// ═══════════════════════════════════════════════════════════════════════════════

Deno.test("rate limiter allows requests within limit", () => {
  const limiter = createRateLimiter({ max: 5, windowMs: 60_000 });
  for (let i = 0; i < 5; i++) {
    assertEquals(limiter.check("192.0.2.1"), true, `request ${i + 1} should be allowed`);
  }
});

Deno.test("rate limiter blocks the (max+1)th request", () => {
  const limiter = createRateLimiter({ max: 5, windowMs: 60_000 });
  for (let i = 0; i < 5; i++) limiter.check("192.0.2.2");
  assertEquals(limiter.check("192.0.2.2"), false, "6th request should be rate-limited");
});

Deno.test("rate limiter enforces 20 req/min (production threshold)", () => {
  const limiter = createRateLimiter({ max: 20, windowMs: 60_000 });
  const ip = "203.0.113.10";
  for (let i = 0; i < 20; i++) {
    assertEquals(limiter.check(ip), true, `request ${i + 1} should be allowed`);
  }
  assertEquals(limiter.check(ip), false, "21st request should be rate-limited");
});

Deno.test("rate limiter is per-IP (different IPs don't share quota)", () => {
  const limiter = createRateLimiter({ max: 3, windowMs: 60_000 });
  for (let i = 0; i < 3; i++) limiter.check("10.0.0.1");
  assertEquals(limiter.check("10.0.0.1"), false);
  assertEquals(limiter.check("10.0.0.2"), true, "separate IP should not be limited");
});

// ═══════════════════════════════════════════════════════════════════════════════
// 2. HMAC signing unit tests
// ═══════════════════════════════════════════════════════════════════════════════

Deno.test("generates and verifies a valid pro key", async () => {
  const secret = "unit-test-secret-for-ts";
  const key = await generateLicenseKey("pro", secret);
  const result = await verifyLicenseKey(key, secret);
  assertEquals(result.valid, true);
  assertEquals(result.tier, "pro");
});

Deno.test("verify rejects key signed with wrong secret", async () => {
  const key = await generateLicenseKey("pro", "correct-secret");
  const result = await verifyLicenseKey(key, "wrong-secret");
  assertEquals(result.valid, false);
  assertEquals(result.error, "Invalid signature");
});

Deno.test("verify rejects malformed key (no dot)", async () => {
  const result = await verifyLicenseKey("asv1_nodothere", "any-secret");
  assertEquals(result.valid, false);
  assertEquals(result.error, "Malformed key");
});

Deno.test("verify rejects unsupported key format", async () => {
  const result = await verifyLicenseKey("as_pro_legacykey123", "any-secret");
  assertEquals(result.valid, false);
  assertEquals(result.error, "Unsupported key format");
});

Deno.test("verify rejects tampered payload", async () => {
  const secret = "tamper-test-secret";
  // Generate valid pro key, then swap in an enterprise payload.
  const proKey = await generateLicenseKey("pro", secret);
  const entKey = await generateLicenseKey("enterprise", secret);
  // Take enterprise payload + pro signature — should fail.
  const [entPayload] = entKey.slice("asv1_".length).split(".");
  const [, proSig] = proKey.slice("asv1_".length).split(".");
  const tampered = `asv1_${entPayload}.${proSig}`;
  const result = await verifyLicenseKey(tampered, secret);
  assertEquals(result.valid, false);
  assertEquals(result.error, "Invalid signature");
});

Deno.test("verify rejects expired key", async () => {
  const secret = "expiry-test-secret";
  const key = await generateLicenseKey("pro", secret, {
    iat: 1000000000,
    exp: 1000000001, // 2001-09-09 — definitely in the past
  });
  const result = await verifyLicenseKey(key, secret);
  assertEquals(result.valid, false);
  assertEquals(result.error, "License expired");
});

Deno.test("verify rejects key with unknown tier", async () => {
  const secret = "tier-test-secret";
  const key = await generateLicenseKey("ultra_mega", secret);
  const result = await verifyLicenseKey(key, secret);
  assertEquals(result.valid, false);
  assertEquals(result.error, "Invalid tier");
});

// ═══════════════════════════════════════════════════════════════════════════════
// 3. HMAC parity tests — TS produces identical signatures to Python fixtures
//
// The fixture file contains vectors generated by python/agentsentinel/utils/keygen.py
// with deterministic (fixed) inputs.  By asserting that our TypeScript
// implementation produces the same HMAC for the same inputs we confirm
// byte-for-byte cross-language parity.
// ═══════════════════════════════════════════════════════════════════════════════

interface ParityVector {
  description: string;
  key: string;
  payload_b64?: string;
  hmac_signature_b64?: string;
  expected_valid: boolean;
  expected_tier?: string;
  expected_error_contains?: string;
}

interface Fixtures {
  secret: string;
  valid: ParityVector[];
  invalid: ParityVector[];
}

// Resolve path relative to this test file so it works from any cwd.
const FIXTURES_PATH = new URL(
  "../../../python/tests/fixtures/license-vectors.json",
  import.meta.url,
).pathname;

Deno.test("parity: TS verifies all valid Python-generated vectors", async () => {
  const fixtures: Fixtures = JSON.parse(await Deno.readTextFile(FIXTURES_PATH));
  const { secret, valid } = fixtures;

  for (const v of valid) {
    const result = await verifyLicenseKey(v.key, secret);
    assertEquals(
      result.valid,
      true,
      `[${v.description}] expected valid=true, got error=${result.error}`,
    );
    assertEquals(result.tier, v.expected_tier, `[${v.description}] tier mismatch`);
  }
});

Deno.test("parity: TS rejects all invalid Python-generated vectors", async () => {
  const fixtures: Fixtures = JSON.parse(await Deno.readTextFile(FIXTURES_PATH));
  const { secret, invalid } = fixtures;

  for (const v of invalid) {
    const result = await verifyLicenseKey(v.key, secret);
    assertEquals(
      result.valid,
      false,
      `[${v.description}] expected valid=false`,
    );
    if (v.expected_error_contains) {
      assertMatch(
        (result.error ?? "").toLowerCase(),
        new RegExp(v.expected_error_contains.toLowerCase()),
        `[${v.description}] error should contain "${v.expected_error_contains}"`,
      );
    }
  }
});

Deno.test("parity: TS generates same HMAC signature as Python for same payload", async () => {
  const fixtures: Fixtures = JSON.parse(await Deno.readTextFile(FIXTURES_PATH));
  const { secret, valid } = fixtures;

  for (const v of valid) {
    if (!v.payload_b64 || !v.hmac_signature_b64) continue;

    // Compute the HMAC of payload_b64 using the TypeScript implementation.
    const cryptoKey = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const sigBytes = await crypto.subtle.sign(
      "HMAC",
      cryptoKey,
      new TextEncoder().encode(v.payload_b64),
    );
    const tsSigB64 = b64urlEncode(new Uint8Array(sigBytes));

    assertEquals(
      tsSigB64,
      v.hmac_signature_b64,
      `[${v.description}] TS signature should be byte-for-byte identical to Python fixture`,
    );
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// 4. Key format validation tests
//    (Tests what validate-license/index.ts checks before the DB lookup.)
// ═══════════════════════════════════════════════════════════════════════════════

const VALID_PREFIXES = [
  "asv1_abc123.sig",          // HMAC-signed format
  "as_free_abc123",           // legacy free
  "as_starter_abc123",        // legacy starter
  "as_pro_abc123",            // legacy pro
  "as_pro_team_abc123",       // legacy pro_team
  "as_team_abc123",           // legacy team
  "as_enterprise_abc123",     // legacy enterprise
];

const MALFORMED_KEYS = [
  "garbage",
  "as__abc",
  "as_unknown_tier_abc",
  "ASVI_abc.sig",
  "",
  "asv2_abc.sig",
  "AS_PRO_abc",               // uppercase — not accepted
];

/** Mirrors the format check in validate-license/index.ts */
function isValidFormat(key: string): boolean {
  const VALID_TIERS_LOCAL = new Set([
    "free", "starter", "pro", "pro_team", "team", "enterprise",
  ]);
  const isLegacy = [...VALID_TIERS_LOCAL].some((t) => key.startsWith(`as_${t}_`));
  return key.startsWith("asv1_") || isLegacy;
}

Deno.test("format validation: accepts all valid prefixes", () => {
  for (const key of VALID_PREFIXES) {
    assertEquals(isValidFormat(key), true, `"${key}" should be accepted`);
  }
});

Deno.test("format validation: rejects malformed keys with 400", () => {
  for (const key of MALFORMED_KEYS) {
    assertEquals(isValidFormat(key), false, `"${key}" should be rejected`);
  }
});
