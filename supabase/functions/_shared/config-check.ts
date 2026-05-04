/**
 * AgentSentinel Edge Function config checker
 *
 * Validates all required Supabase / Edge Function environment variables
 * and prints a pass/fail table.
 *
 * Usage (from repo root):
 *   deno run supabase/functions/_shared/config-check.ts
 *   deno run supabase/functions/_shared/config-check.ts --mode dev
 *   deno run supabase/functions/_shared/config-check.ts --mode prod
 *   deno run supabase/functions/_shared/config-check.ts --env-file supabase/.env
 *
 * Exit codes:
 *   0 — all required variables are present and valid
 *   1 — one or more required variables are missing or invalid
 */

// ─── types ───────────────────────────────────────────────────────────────────

interface VarSpec {
  name: string;
  requiredDev: boolean;
  requiredProd: boolean;
  description: string;
  validator?: (value: string) => string | null;
}

// ─── validators ──────────────────────────────────────────────────────────────

function minLen(n: number) {
  return (v: string): string | null =>
    v.length < n ? `must be at least ${n} characters (got ${v.length})` : null;
}

function startsWith(...prefixes: string[]) {
  return (v: string): string | null =>
    prefixes.some((p) => v.startsWith(p))
      ? null
      : `must start with one of ${JSON.stringify(prefixes)}`;
}

function isUrl() {
  return (v: string): string | null =>
    v.startsWith("http://") || v.startsWith("https://")
      ? null
      : "must be a URL starting with http:// or https://";
}

// ─── variable registry ────────────────────────────────────────────────────────

const VARS: VarSpec[] = [
  // ── Supabase ──────────────────────────────────────────────────────────────
  {
    name: "SUPABASE_URL",
    requiredDev: true,
    requiredProd: true,
    description: "Supabase project URL",
    validator: isUrl(),
  },
  {
    name: "SUPABASE_SERVICE_ROLE_KEY",
    requiredDev: true,
    requiredProd: true,
    description: "Supabase service-role key (server-side only)",
    validator: minLen(20),
  },
  // ── License signing secret ────────────────────────────────────────────────
  {
    name: "AGENTSENTINEL_LICENSE_SIGNING_SECRET",
    requiredDev: true,
    requiredProd: true,
    description: "HMAC secret for license key signing/verification",
    validator: minLen(32),
  },
  // ── Admin API secret ──────────────────────────────────────────────────────
  {
    name: "ADMIN_API_SECRET",
    requiredDev: true,
    requiredProd: true,
    description: "Bearer token for admin-only endpoints",
    validator: minLen(32),
  },
  // ── Stripe ────────────────────────────────────────────────────────────────
  {
    name: "STRIPE_SECRET_KEY",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe secret API key",
    validator: startsWith("sk_live_", "sk_test_"),
  },
  {
    name: "STRIPE_WEBHOOK_SECRET",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe webhook signing secret",
    validator: startsWith("whsec_"),
  },
  {
    name: "STRIPE_PRICE_STARTER",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe Price ID for Starter tier",
    validator: startsWith("price_"),
  },
  {
    name: "STRIPE_PRICE_PRO",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe Price ID for Pro tier",
    validator: startsWith("price_"),
  },
  {
    name: "STRIPE_PRICE_PRO_TEAM",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe Price ID for Pro Team tier",
    validator: startsWith("price_"),
  },
  {
    name: "STRIPE_PRICE_ENTERPRISE",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe Price ID for Enterprise tier",
    validator: startsWith("price_"),
  },
  {
    name: "STRIPE_PRICE_PRO_TEAM_BASE",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe Price ID for Pro Team base charge",
    validator: startsWith("price_"),
  },
  {
    name: "STRIPE_PRICE_PRO_TEAM_SEAT",
    requiredDev: false,
    requiredProd: true,
    description: "Stripe Price ID for Pro Team per-seat charge",
    validator: startsWith("price_"),
  },
  // ── Email ─────────────────────────────────────────────────────────────────
  {
    name: "RESEND_API_KEY",
    requiredDev: false,
    requiredProd: true,
    description: "Resend API key for transactional email",
    validator: startsWith("re_"),
  },
  // ── Site URL ──────────────────────────────────────────────────────────────
  {
    name: "SITE_BASE_URL",
    requiredDev: false,
    requiredProd: true,
    description: "Site base URL (used for Stripe redirects)",
    validator: isUrl(),
  },
];

// ─── .env file parser ─────────────────────────────────────────────────────────

function loadEnvFile(path: string): Record<string, string> {
  const env: Record<string, string> = {};
  let text: string;
  try {
    text = Deno.readTextFileSync(path);
  } catch {
    return env;
  }
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if (val.length >= 2 && val[0] === val[val.length - 1] && (val[0] === '"' || val[0] === "'")) {
      val = val.slice(1, -1);
    }
    env[key] = val;
  }
  return env;
}

// ─── colour helpers ───────────────────────────────────────────────────────────

const isTty = Deno.stdout.isTerminal();

function green(s: string) { return isTty ? `\x1b[0;32m${s}\x1b[0m` : s; }
function red(s: string)   { return isTty ? `\x1b[0;31m${s}\x1b[0m` : s; }
function dim(s: string)   { return isTty ? `\x1b[2m${s}\x1b[0m` : s; }

// ─── runner ───────────────────────────────────────────────────────────────────

function runCheck(env: Record<string, string>, devMode: boolean): number {
  const mode = devMode ? "dev" : "prod";
  const colName = 42;
  const colDesc = 45;

  const header = `${"Variable".padEnd(colName)}  ${"Description".padEnd(colDesc)}  Status`;
  const sep = "─".repeat(header.length);

  console.log(`\nAgentSentinel config check  (mode: ${mode})\n${sep}`);
  console.log(header);
  console.log(sep);

  let failures = 0;

  for (const spec of VARS) {
    const required = devMode ? spec.requiredDev : spec.requiredProd;
    const value = env[spec.name] ?? "";

    let status: string;
    if (!value) {
      if (required) {
        status = red("✗  MISSING");
        failures++;
      } else {
        status = dim("·  optional");
      }
    } else if (spec.validator) {
      const error = spec.validator(value);
      if (error) {
        status = red(`✗  ${error.slice(0, 30)}`);
        failures++;
      } else {
        status = green("✓  ok");
      }
    } else {
      status = green("✓  ok");
    }

    const namePad = spec.name.slice(0, colName).padEnd(colName);
    const descPad = spec.description.slice(0, colDesc).padEnd(colDesc);
    console.log(`${namePad}  ${descPad}  ${status}`);
  }

  console.log(sep);
  if (failures === 0) {
    console.log(green(`All checks passed  (${VARS.length} variables checked, mode=${mode})`));
  } else {
    console.log(red(`${failures} check(s) failed  (mode=${mode})`));
  }
  console.log();

  return failures;
}

// ─── CLI ─────────────────────────────────────────────────────────────────────

const args = Deno.args;
let envFile: string | null = null;
let modeOverride: "dev" | "prod" | null = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--env-file" && args[i + 1]) {
    envFile = args[++i];
  } else if (args[i] === "--mode" && args[i + 1]) {
    const m = args[++i];
    if (m === "dev" || m === "prod") {
      modeOverride = m;
    } else {
      console.error(`Unknown mode: ${m}  (must be dev or prod)`);
      Deno.exit(1);
    }
  } else if (args[i] === "--help") {
    console.log(
      "Usage: deno run supabase/functions/_shared/config-check.ts [--env-file PATH] [--mode dev|prod]",
    );
    Deno.exit(0);
  }
}

// Collect env: Deno.env first (already-set secrets), then overlay from file
const combined: Record<string, string> = { ...Object.fromEntries(Deno.env.toObject()) };

const filePaths = envFile ? [envFile] : ["supabase/.env", ".env"];
let anyFound = false;
for (const p of filePaths) {
  const loaded = loadEnvFile(p);
  if (Object.keys(loaded).length > 0) {
    Object.assign(combined, loaded);
    console.log(`Loaded ${p}  (${Object.keys(loaded).length} variables)`);
    anyFound = true;
  }
}

if (!anyFound && !Object.keys(combined).some((k) => k.startsWith("SUPABASE"))) {
  console.error(
    "No .env file found and no Supabase env vars detected.  " +
      "Run ./scripts/setup-env.sh first, or pass --env-file <path>.",
  );
  Deno.exit(1);
}

const devMode =
  modeOverride !== null
    ? modeOverride === "dev"
    : combined["AGENTSENTINEL_DEV"] === "1" ||
      combined["AGENTSENTINEL_DEV_MODE"]?.toLowerCase() === "true";

const failures = runCheck(combined, devMode);
Deno.exit(failures === 0 ? 0 : 1);
