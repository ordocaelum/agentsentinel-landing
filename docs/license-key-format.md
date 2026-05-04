# License Key Format — Canonical Specification

> **Status:** Production  
> **Applies to:** AgentSentinel SDK v1.2+ and all Supabase Edge Functions

---

## Overview

AgentSentinel issues two families of license keys:

| Family | Prefix | Description |
|---|---|---|
| `asv1_*` | HMAC-signed | Current format — carries embedded tier and expiry, verifiable offline |
| `as_<tier>_*` | Legacy | Random suffix, requires database lookup to validate |

New licenses issued since SDK v1.2 use the `asv1_*` format.  The legacy format is still accepted by the validate-license endpoint for backward compatibility.

---

## `asv1_*` Key Format

```
asv1_<payload_b64>.<sig_b64>
```

| Component | Description |
|---|---|
| `asv1_` | Fixed prefix (version sentinel) |
| `payload_b64` | Base64url-encoded JSON payload (no padding `=`) |
| `.` | Literal separator |
| `sig_b64` | Base64url-encoded HMAC-SHA256 signature (no padding `=`) |

### Payload JSON

The payload is a compact JSON object with **keys sorted alphabetically**:

```json
{"exp":1731536000,"iat":1700000000,"nonce":"abc123defghi","tier":"pro"}
```

| Field | Type | Description |
|---|---|---|
| `exp` | integer | Unix timestamp (seconds) — key expiry |
| `iat` | integer | Unix timestamp (seconds) — key issuance time |
| `nonce` | string | Random base64url value (prevents pre-computation attacks) |
| `tier` | string | License tier (see [Tiers](#valid-tier-values)) |

> **Key ordering rule:** Keys **must** be sorted lexicographically (alphabetical).  
> In Python this is achieved with `json.dumps(payload, sort_keys=True, separators=(",", ":"))`.  
> In TypeScript it is achieved with `JSON.stringify(payload, ["exp", "iat", "nonce", "tier"])`.  
> Both produce byte-for-byte identical JSON for the same input values.

### Signing Algorithm

```
sig_b64 = base64url( HMAC-SHA256( signing_secret, payload_b64 ) )
```

- **Algorithm:** HMAC-SHA256
- **Key:** `AGENTSENTINEL_LICENSE_SIGNING_SECRET` (UTF-8 encoded)
- **Message:** `payload_b64` as a UTF-8 string (not the decoded JSON bytes)
- **Output encoding:** Base64url **without padding** (`=` stripped)

The signing operation is applied to the already-encoded `payload_b64` string, not to the raw JSON bytes.  This means you must base64url-encode the payload first, then HMAC-sign the resulting string.

### Reference Implementations

**Python** (`python/agentsentinel/utils/keygen.py`):

```python
import base64, hashlib, hmac, json, os, secrets, time

def generate_license_key(tier: str, valid_days: int = 365, secret: str = None) -> str:
    signing_secret = secret or os.environ["AGENTSENTINEL_LICENSE_SIGNING_SECRET"]
    now = int(time.time())
    payload = {"exp": now + valid_days * 86400, "iat": now,
               "nonce": secrets.token_urlsafe(12), "tier": tier.lower()}
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    sig = hmac.new(signing_secret.encode(), payload_b64.encode(), hashlib.sha256)
    sig_b64 = base64.urlsafe_b64encode(sig.digest()).decode().rstrip("=")
    return f"asv1_{payload_b64}.{sig_b64}"
```

**TypeScript / Deno** (from `supabase/functions/stripe-webhook/index.ts`):

```typescript
async function generateLicenseKey(tier: string, secret: string): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const nonce = b64urlEncode(crypto.getRandomValues(new Uint8Array(9)));
  const payloadJson = JSON.stringify(
    { exp: now + 365 * 86400, iat: now, nonce, tier: tier.toLowerCase() },
    ["exp", "iat", "nonce", "tier"],  // ← sorts keys alphabetically
  );
  const payloadB64 = b64urlEncode(new TextEncoder().encode(payloadJson));
  const key = await crypto.subtle.importKey("raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payloadB64));
  return `asv1_${payloadB64}.${b64urlEncode(new Uint8Array(sig))}`;
}
```

---

## Valid Tier Values

| Tier value | Display name | Max agents | Max events/month |
|---|---|---|---|
| `free` | Free | 1 | 1,000 |
| `starter` | Starter | 1 | 1,000 |
| `pro` | Pro | 5 | 50,000 |
| `pro_team` | Pro Team | 5 | 50,000 |
| `team` | Team | 20 | 500,000 |
| `enterprise` | Enterprise | Unlimited | Unlimited |

See `supabase/functions/_shared/tiers.ts` (TypeScript) and `python/agentsentinel/licensing.py` (Python) for the authoritative tier definitions — both must be kept in sync.

---

## Legacy Key Format

```
as_<tier>_<random>
```

Where `<tier>` is one of the valid tier values and `<random>` is a 16-character hex string.  Legacy keys carry no embedded claims; their validity, tier, and expiry are stored solely in the database.

**Legacy keys cannot be verified offline.**

---

## Cross-Language Parity

The signing algorithm is designed to produce byte-for-byte identical output in Python and TypeScript.  The key insight is that both implementations produce the same canonical JSON by:

1. Including exactly four fields: `exp`, `iat`, `nonce`, `tier`
2. Sorting keys alphabetically (Python `sort_keys=True` / TypeScript replacer array `["exp","iat","nonce","tier"]`)
3. Using compact JSON (no spaces): Python `separators=(",",":")` / TypeScript default `JSON.stringify`
4. Base64url encoding without padding in both languages

The parity test suite is in:
- `supabase/functions/validate-license/test.ts` (TypeScript/Deno)
- `python/tests/test_licensing_parity.py` (Python/pytest)
- `python/tests/fixtures/license-vectors.json` (shared test vectors)

---

## Offline Verification

The Python SDK performs offline verification when the license API is unreachable:

1. Check key starts with `asv1_`
2. Split on the last `.` to get `payload_b64` and `sig_b64`
3. Recompute `expected_sig = HMAC-SHA256(signing_secret, payload_b64)`
4. Compare `expected_sig` with `sig_b64` using a constant-time comparator
5. Decode `payload_b64` → JSON → extract `tier` and `exp`
6. Validate `tier` against the allowlist and check `exp > now`

No database or network call is required, assuming `AGENTSENTINEL_LICENSE_SIGNING_SECRET` is set.

---

## Key Rotation

To rotate the signing secret:

1. Generate a new high-entropy secret: `openssl rand -base64 48`
2. Update `AGENTSENTINEL_LICENSE_SIGNING_SECRET` in your Supabase secrets:  
   `supabase secrets set AGENTSENTINEL_LICENSE_SIGNING_SECRET=<new_secret>`
3. Re-issue all active licenses (re-run key generation with the new secret).  
   Old keys signed with the previous secret will fail offline verification but  
   still pass database validation until they are re-keyed or expire.
4. Update the secret in all Python SDK deployments:  
   `AGENTSENTINEL_LICENSE_SIGNING_SECRET=<new_secret>` in each service's environment.
5. Old `asv1_*` keys signed with the rotated secret will be rejected offline  
   after the rotation.  Customers should be notified to update their keys.

> **Important:** Never commit the signing secret to source control.  
> Rotate immediately if the secret is exposed.
