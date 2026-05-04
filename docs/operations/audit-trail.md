# Audit Trail Operations Guide

This document describes the `admin_logs` schema, how admin actions are recorded, the data retention policy, and how to query the audit trail for compliance reviews.

## Table of Contents

1. [Schema Reference](#schema-reference)
2. [Sensitive Field Masking](#sensitive-field-masking)
3. [What Is Logged](#what-is-logged)
4. [Querying the Audit Trail](#querying-the-audit-trail)
5. [Data Retention Policy](#data-retention-policy)
6. [Compliance Queries](#compliance-queries)

---

## Schema Reference

Migration: `supabase/migrations/011_admin_tables.sql`

```sql
CREATE TABLE admin_logs (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  admin_id    TEXT NOT NULL,    -- email or user ID of the actor
  action      TEXT NOT NULL,    -- 'created', 'updated', 'deleted', 'revoked', 'activated', etc.
  entity_type TEXT NOT NULL,    -- 'license', 'promo', 'user', 'system', etc.
  entity_id   UUID,             -- ID of the affected row (nullable for system-level actions)
  old_values  JSONB,            -- state before the change (sensitive fields masked)
  new_values  JSONB,            -- state after the change (sensitive fields masked)
  ip_address  TEXT,
  user_agent  TEXT,
  status      TEXT DEFAULT 'success' CHECK (status IN ('success', 'failure')),
  error_message TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### Indexes

| Index                    | Column(s)                   | Purpose                                   |
|--------------------------|-----------------------------|-------------------------------------------|
| `idx_admin_logs_admin`   | `admin_id`                  | Filter by actor                           |
| `idx_admin_logs_entity`  | `(entity_type, entity_id)`  | Find all actions on a specific entity     |
| `idx_admin_logs_created` | `created_at DESC`           | Recent-first queries without seq-scan     |

### Row Level Security

- All rows are **immutable** once inserted (no UPDATE or DELETE policies granted).
- Only the `service_role` can insert rows (Edge Functions / backend).
- Authenticated admin users can SELECT rows via the admin dashboard.

---

## Sensitive Field Masking

Before any `old_values` or `new_values` object is written to `admin_logs`, the `auditAPI.log()` function in `static/admin/js/api.js` applies the `maskSensitiveFields()` helper.

**Rule:** Any key in the logged object whose name matches the regular expression `/secret|key|token|password/i` has its value replaced with:

```
<first 8 hex chars of SHA-256(original_value)>...
```

**Example:**

```json
// Before masking (never persisted)
{
  "license_key": "asv1_eyJleHAiOjE3...",
  "tier": "pro",
  "admin_api_secret": "sk-live-abc123"
}

// After masking (what is stored in admin_logs)
{
  "license_key": "a1b2c3d4...",
  "tier": "pro",
  "admin_api_secret": "deadbeef..."
}
```

The masking is:
- **Recursive** — nested objects and arrays are walked.
- **Applied client-side** in the admin dashboard JS before the Supabase REST call.
- **Deterministic** — the same value always produces the same mask prefix, useful for correlating logs without exposing the raw value.

---

## What Is Logged

### License actions (`entity_type = 'license'`)

| Action       | Trigger                                                |
|--------------|--------------------------------------------------------|
| `revoked`    | Admin clicks Revoke in the Licenses page               |
| `activated`  | Admin clicks Activate (re-enables a revoked license)   |
| `deleted`    | Admin permanently deletes a license                    |

### Promo code actions (`entity_type = 'promo'`)

| Action     | Trigger                                    |
|------------|--------------------------------------------|
| `created`  | Admin creates a new promo code             |
| `updated`  | Admin edits an existing promo              |
| `deleted`  | Admin deletes a promo code                 |
| `disabled` | Admin disables a promo (sets active=false) |
| `enabled`  | Admin re-enables a promo                   |

### System / webhook actions

| Action        | Trigger                                         |
|---------------|-------------------------------------------------|
| `webhook_replayed` | Admin manually replays a webhook event     |

---

## Querying the Audit Trail

### All actions by a specific admin in the last 7 days

```sql
SELECT
  created_at,
  action,
  entity_type,
  entity_id,
  status
FROM admin_logs
WHERE admin_id = 'admin@example.com'
  AND created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
```

### All actions on a specific license

```sql
SELECT *
FROM admin_logs
WHERE entity_type = 'license'
  AND entity_id = '<license-uuid>'
ORDER BY created_at DESC;
```

### All failed admin actions in the last 30 days

```sql
SELECT *
FROM admin_logs
WHERE status = 'failure'
  AND created_at > NOW() - INTERVAL '30 days'
ORDER BY created_at DESC;
```

### Promo code creation log with before/after values

```sql
SELECT
  created_at,
  admin_id,
  action,
  new_values->>'code'   AS code,
  new_values->>'type'   AS type,
  new_values->>'value'  AS value,
  new_values->>'active' AS active
FROM admin_logs
WHERE entity_type = 'promo'
  AND action = 'created'
ORDER BY created_at DESC
LIMIT 50;
```

### Volume by action type (compliance summary)

```sql
SELECT
  action,
  entity_type,
  COUNT(*) AS total,
  MIN(created_at) AS earliest,
  MAX(created_at) AS latest
FROM admin_logs
GROUP BY action, entity_type
ORDER BY total DESC;
```

---

## Data Retention Policy

| Period            | Policy                                                                 |
|-------------------|------------------------------------------------------------------------|
| 0 – 90 days       | All rows retained in `admin_logs` (hot storage, indexed).              |
| 91 days – 2 years | Rows may be archived to cold storage (e.g. Supabase Storage as JSONL). |
| > 2 years         | Rows may be deleted unless required by applicable regulation.          |

> **Regulatory note:** If your deployment is subject to SOC 2, GDPR, HIPAA, or similar, retain logs for the duration required by your compliance framework and consult your legal team before enabling automatic deletion.

### Manual archival query

To export rows older than 90 days before pruning:

```sql
COPY (
  SELECT * FROM admin_logs
  WHERE created_at < NOW() - INTERVAL '90 days'
  ORDER BY created_at
) TO '/tmp/admin_logs_archive.csv' CSV HEADER;
```

### Pruning old rows

```sql
-- Only run after archiving (see above)
DELETE FROM admin_logs
WHERE created_at < NOW() - INTERVAL '730 days'; -- 2 years
```

---

## Compliance Queries

### Prove a user's data was not accessed without authorisation (GDPR Article 32)

```sql
SELECT
  created_at,
  admin_id,
  action,
  entity_type,
  entity_id,
  ip_address
FROM admin_logs
WHERE new_values::text LIKE '%customer@example.com%'
   OR old_values::text LIKE '%customer@example.com%'
ORDER BY created_at DESC;
```

### Segregation of duties check — who deleted licenses?

```sql
SELECT DISTINCT admin_id
FROM admin_logs
WHERE action = 'deleted'
  AND entity_type = 'license';
```

### Audit log integrity check — confirm no rows have been deleted

The `admin_logs` table has no `DELETE` RLS policy, so row counts should only ever increase.  You can snapshot the count at the start of an audit period and verify it has not decreased:

```sql
SELECT COUNT(*) FROM admin_logs;
-- Store this value; re-run at the end of the audit period and confirm it is >= the stored value.
```
