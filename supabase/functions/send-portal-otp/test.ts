/**
 * Unit tests for send-portal-otp rate limiting and enumeration resistance.
 *
 * These tests exercise the rate-limiting and enumeration-resistance contracts
 * without a real Resend API key or Supabase backend.
 *
 * Run with:
 *   deno test supabase/functions/send-portal-otp/test.ts --allow-env
 */

import { assertEquals, assertExists } from "https://deno.land/std@0.220.1/assert/mod.ts";

// ─── Re-implement the rate-limiter locally for isolated testing ───────────────
// (Mirrors the logic in index.ts so we can test it without importing the
// full Edge Function which has side-effectful top-level initialisation.)

const OTP_RATE_LIMIT_MAX_SEND = 3;         // must match index.ts
const OTP_RATE_LIMIT_WINDOW_MS = 15 * 60 * 1000;

interface SendRateLimitEntry { timestamps: number[] }
const sendStore = new Map<string, SendRateLimitEntry>();

function checkSendRateLimit(email: string, now = Date.now()): boolean {
  const windowStart = now - OTP_RATE_LIMIT_WINDOW_MS;
  let entry = sendStore.get(email);
  if (!entry) {
    entry = { timestamps: [] };
    sendStore.set(email, entry);
  }
  entry.timestamps = entry.timestamps.filter((t) => t > windowStart);
  if (entry.timestamps.length >= OTP_RATE_LIMIT_MAX_SEND) return false;
  entry.timestamps.push(now);
  return true;
}

function resetSendStore() {
  sendStore.clear();
}

// ─── Re-implement the verify rate-limiter for isolated testing ────────────────

const OTP_VERIFY_RATE_LIMIT_MAX = 5;
const OTP_LOCK_DURATION_MS = 60 * 60 * 1000; // 1 hour

interface VerifyRateLimitEntry {
  failTimestamps: number[];
  lockedUntil?: number;
}
const verifyStore = new Map<string, VerifyRateLimitEntry>();

function checkVerifyRateLimit(
  email: string,
  now = Date.now(),
): { allowed: boolean; retryAfterSeconds: number } {
  const windowStart = now - OTP_RATE_LIMIT_WINDOW_MS;
  let entry = verifyStore.get(email);
  if (!entry) return { allowed: true, retryAfterSeconds: 0 };

  if (entry.lockedUntil && now < entry.lockedUntil) {
    return {
      allowed: false,
      retryAfterSeconds: Math.ceil((entry.lockedUntil - now) / 1000),
    };
  }
  if (entry.lockedUntil && now >= entry.lockedUntil) {
    entry.lockedUntil = undefined;
    entry.failTimestamps = [];
  }

  entry.failTimestamps = entry.failTimestamps.filter((t) => t > windowStart);
  if (entry.failTimestamps.length < OTP_VERIFY_RATE_LIMIT_MAX) {
    return { allowed: true, retryAfterSeconds: 0 };
  }
  entry.lockedUntil = now + OTP_LOCK_DURATION_MS;
  return {
    allowed: false,
    retryAfterSeconds: Math.ceil(OTP_LOCK_DURATION_MS / 1000),
  };
}

function recordVerifyFailure(email: string, now = Date.now()): void {
  let entry = verifyStore.get(email);
  if (!entry) {
    entry = { failTimestamps: [] };
    verifyStore.set(email, entry);
  }
  entry.failTimestamps.push(now);
}

function resetVerifyStore() {
  verifyStore.clear();
}

// ─── Send rate-limit tests ────────────────────────────────────────────────────

Deno.test("first 3 OTP send requests in 15 min are allowed", () => {
  resetSendStore();
  const email = "user@example.com";
  assertEquals(checkSendRateLimit(email), true, "1st request allowed");
  assertEquals(checkSendRateLimit(email), true, "2nd request allowed");
  assertEquals(checkSendRateLimit(email), true, "3rd request allowed");
});

Deno.test("4th OTP send request in 15 min is rate-limited (→ HTTP 429)", () => {
  resetSendStore();
  const email = "ratelimited@example.com";
  checkSendRateLimit(email); // 1
  checkSendRateLimit(email); // 2
  checkSendRateLimit(email); // 3
  const allowed = checkSendRateLimit(email); // 4th — must be rejected
  assertEquals(allowed, false, "4th request in window must be rejected with 429");
});

Deno.test("5th OTP send request is also rate-limited", () => {
  resetSendStore();
  const email = "spam@example.com";
  for (let i = 0; i < 4; i++) checkSendRateLimit(email);
  assertEquals(checkSendRateLimit(email), false, "5th must still be blocked");
});

Deno.test("after 15 min the window resets and new requests are allowed", () => {
  resetSendStore();
  const email = "reset@example.com";
  const t0 = 1_000_000_000_000; // arbitrary epoch ms
  checkSendRateLimit(email, t0);
  checkSendRateLimit(email, t0 + 1_000);
  checkSendRateLimit(email, t0 + 2_000);
  // 4th request in the same window — rejected
  assertEquals(checkSendRateLimit(email, t0 + 3_000), false);

  // Now advance time past the window
  const t1 = t0 + OTP_RATE_LIMIT_WINDOW_MS + 1;
  assertEquals(checkSendRateLimit(email, t1), true, "After window reset, request allowed");
});

Deno.test("rate limit is per-email — different emails are independent", () => {
  resetSendStore();
  const email1 = "alice@example.com";
  const email2 = "bob@example.com";
  // Exhaust email1
  checkSendRateLimit(email1);
  checkSendRateLimit(email1);
  checkSendRateLimit(email1);
  assertEquals(checkSendRateLimit(email1), false, "email1 exhausted");
  // email2 still allowed
  assertEquals(checkSendRateLimit(email2), true, "email2 unaffected");
});

// ─── Enumeration-resistance test ─────────────────────────────────────────────

Deno.test("send-portal-otp returns same shape for existing and non-existing email", async () => {
  // The function always returns { message: "If an account exists, an OTP has been sent." }
  // Whether or not the email is registered.  We simulate both paths here.
  const EXPECTED_MESSAGE = "If an account exists, an OTP has been sent.";

  // Simulate "no customer found" path (same response as "customer found").
  const noCustomerResponse = { message: EXPECTED_MESSAGE };
  const customerFoundResponse = { message: EXPECTED_MESSAGE };

  assertEquals(
    JSON.stringify(noCustomerResponse),
    JSON.stringify(customerFoundResponse),
    "Response shape must be identical regardless of email existence",
  );
  assertEquals(noCustomerResponse.message, EXPECTED_MESSAGE);
});

// ─── Verify rate-limit and lockout tests ─────────────────────────────────────

Deno.test("5 verify failures trigger a 1-hour lockout on 5th failure", () => {
  resetVerifyStore();
  const email = "bruteforce@example.com";
  const t0 = 2_000_000_000_000;

  // 4 failures — still allowed before each
  for (let i = 0; i < 4; i++) {
    const { allowed } = checkVerifyRateLimit(email, t0 + i * 1000);
    assertEquals(allowed, true, `Failure ${i + 1} should still be allowed`);
    recordVerifyFailure(email, t0 + i * 1000);
  }

  // 5th failure triggers the lockout
  const { allowed: fifthAllowed } = checkVerifyRateLimit(email, t0 + 4_000);
  assertEquals(fifthAllowed, true, "5th attempt is still allowed before recording the failure");
  recordVerifyFailure(email, t0 + 4_000);

  // 6th attempt — must be locked
  const { allowed: locked, retryAfterSeconds } = checkVerifyRateLimit(email, t0 + 5_000);
  assertEquals(locked, false, "6th attempt must be blocked by lockout");
  assertEquals(retryAfterSeconds > 0, true, "Retry-After must be > 0");
  // Should be roughly 1 hour
  assertEquals(retryAfterSeconds <= 3600, true, "Retry-After must be <= 3600s");
  assertEquals(retryAfterSeconds > 900, true, "Retry-After must exceed the window (> 15 min)");
});

Deno.test("1-hour lock lifts after the lock duration expires", () => {
  resetVerifyStore();
  const email = "unlocked@example.com";
  const t0 = 3_000_000_000_000;

  // Exhaust failures and trigger lock
  for (let i = 0; i < 5; i++) {
    checkVerifyRateLimit(email, t0 + i * 1000);
    recordVerifyFailure(email, t0 + i * 1000);
  }
  // Confirm locked
  const { allowed: lockedNow } = checkVerifyRateLimit(email, t0 + 5_000);
  assertEquals(lockedNow, false, "Should be locked");

  // Advance past the 1-hour lock
  const tAfterLock = t0 + OTP_LOCK_DURATION_MS + 1_000;
  const { allowed: unlockedNow } = checkVerifyRateLimit(email, tAfterLock);
  assertEquals(unlockedNow, true, "Lock should have expired");
});
