#!/bin/sh
# scripts/setup-env.sh
#
# AgentSentinel environment bootstrap — POSIX sh (works on bash, dash, zsh)
#
# Usage:
#   ./scripts/setup-env.sh                         # create .env files from templates
#   ./scripts/setup-env.sh --force                 # overwrite existing .env files
#   ./scripts/setup-env.sh --dry-run               # print what would be written, make no changes
#   ./scripts/setup-env.sh --regenerate KEY        # regenerate a single named secret in place
#
# What it does:
#   1. Copies .env.example       → .env
#      Copies supabase/.env.example → supabase/.env
#   2. Replaces placeholder tokens with generated values:
#        __GENERATE_HEX_32__    → openssl rand -hex 32     (64-char hex string)
#        __GENERATE_BASE64_64__ → openssl rand -base64 64  (88-char base64 string)
#        __GENERATE_UUID__      → uuidgen or /proc/sys/kernel/random/uuid
#   3. Prints a table of which keys were auto-generated vs. left for manual entry.
#
# Idempotent: re-running without --force does nothing if .env already exists.
# Use --regenerate <KEY> to rotate a single secret without touching the rest.

set -eu

# ─── colours ─────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    RED="\033[0;31m"
    CYAN="\033[0;36m"
    BOLD="\033[1m"
    RESET="\033[0m"
else
    GREEN=""; YELLOW=""; RED=""; CYAN=""; BOLD=""; RESET=""
fi

# ─── helpers ─────────────────────────────────────────────────────────────────
info()    { printf "${CYAN}[setup-env]${RESET} %s\n" "$*"; }
success() { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${RESET}  %s\n" "$*"; }
err()     { printf "${RED}✗${RESET}  %s\n" "$*" >&2; }
die()     { err "$*"; exit 1; }

# ─── generate secret value ───────────────────────────────────────────────────
# Outputs a generated value for the given placeholder token.
gen_value() {
    placeholder="$1"
    case "$placeholder" in
        __GENERATE_HEX_32__)
            openssl rand -hex 32
            ;;
        __GENERATE_BASE64_64__)
            openssl rand -base64 64 | tr -d '\n'
            ;;
        __GENERATE_UUID__)
            if command -v uuidgen >/dev/null 2>&1; then
                uuidgen | tr '[:upper:]' '[:lower:]'
            elif [ -r /proc/sys/kernel/random/uuid ]; then
                cat /proc/sys/kernel/random/uuid
            else
                # fallback: construct UUID-shaped hex via openssl
                h=$(openssl rand -hex 16)
                printf '%s-%s-%s-%s-%s\n' \
                    "$(printf '%s' "$h" | cut -c1-8)" \
                    "$(printf '%s' "$h" | cut -c9-12)" \
                    "$(printf '%s' "$h" | cut -c13-16)" \
                    "$(printf '%s' "$h" | cut -c17-20)" \
                    "$(printf '%s' "$h" | cut -c21-32)"
            fi
            ;;
        *)
            die "Unknown placeholder token: $placeholder"
            ;;
    esac
}

# ─── process one .env file ───────────────────────────────────────────────────
# process_file <src> <dst> <dry_run> [regenerate_key]
# Replaces __GENERATE_*__ tokens in <src>, writes to <dst>.
# Prints a summary of generated vs. manual keys.
process_file() {
    src="$1"
    dst="$2"
    dry_run="$3"
    regen_key="${4:-}"

    generated_keys=""
    manual_keys=""

    # Build the output line by line
    output=""
    while IFS= read -r line || [ -n "$line" ]; do
        # Match lines of the form KEY=__GENERATE_*__
        case "$line" in
            \#*|"")
                output="${output}${line}
"
                continue
                ;;
        esac

        key="${line%%=*}"
        val="${line#*=}"

        case "$val" in
            __GENERATE_*)
                # If --regenerate was given and this isn't the target key, skip generation
                if [ -n "$regen_key" ] && [ "$key" != "$regen_key" ]; then
                    # Read the current value from dst if it exists, else keep placeholder
                    if [ -f "$dst" ]; then
                        existing_val=$(grep -m1 "^${key}=" "$dst" 2>/dev/null | cut -d= -f2- || true)
                        if [ -n "$existing_val" ]; then
                            output="${output}${key}=${existing_val}
"
                            continue
                        fi
                    fi
                    output="${output}${line}
"
                    continue
                fi

                new_val=$(gen_value "$val")
                output="${output}${key}=${new_val}
"
                generated_keys="${generated_keys} ${key}"
                ;;
            ""|*_here|*_xxxxx|*_here*)
                # Empty or obvious placeholder — mark as manual entry needed
                output="${output}${line}
"
                if [ -n "$key" ] && [ "$key" != "$line" ]; then
                    manual_keys="${manual_keys} ${key}"
                fi
                ;;
            *)
                output="${output}${line}
"
                ;;
        esac
    done < "$src"

    if [ "$dry_run" = "yes" ]; then
        printf "\n${BOLD}─── dry-run: would write %s ───${RESET}\n" "$dst"
        printf '%s' "$output"
        printf "${BOLD}──────────────────────────────────────${RESET}\n\n"
    else
        # Write atomically via temp file
        tmp="${dst}.tmp.$$"
        printf '%s' "$output" > "$tmp"
        mv "$tmp" "$dst"
    fi

    # Print summary
    if [ -n "$generated_keys" ]; then
        for k in $generated_keys; do
            success "Generated  $k"
        done
    fi
    if [ -n "$manual_keys" ]; then
        for k in $manual_keys; do
            warn "Manual     $k  ← fill in manually"
        done
    fi
}

# ─── regenerate a single key in an existing .env file ────────────────────────
# regen_in_file <dst> <key>
regen_in_file() {
    dst="$1"
    key="$2"

    if [ ! -f "$dst" ]; then
        die "$dst does not exist. Run setup-env.sh first."
    fi

    # Find the placeholder token for this key from the corresponding example file
    # Try both example paths
    example=""
    dir=$(dirname "$dst")
    if [ -f "${dir}/.env.example" ]; then
        example="${dir}/.env.example"
    elif [ -f ".env.example" ]; then
        example=".env.example"
    fi

    placeholder=""
    if [ -n "$example" ]; then
        placeholder=$(grep -m1 "^${key}=" "$example" 2>/dev/null | cut -d= -f2- || true)
    fi

    # Default to HEX_32 if we can't find the placeholder
    case "$placeholder" in
        __GENERATE_*) : ;;
        *) placeholder="__GENERATE_HEX_32__" ;;
    esac

    new_val=$(gen_value "$placeholder")

    # Replace the line in dst
    tmp="${dst}.tmp.$$"
    sed "s|^${key}=.*|${key}=${new_val}|" "$dst" > "$tmp" && mv "$tmp" "$dst"
    success "Regenerated  $key  in $dst"
}

# ─── parse args ──────────────────────────────────────────────────────────────
FORCE="no"
DRY_RUN="no"
REGEN_KEY=""

while [ $# -gt 0 ]; do
    case "$1" in
        --force)
            FORCE="yes"
            shift
            ;;
        --dry-run)
            DRY_RUN="yes"
            shift
            ;;
        --regenerate)
            [ $# -ge 2 ] || die "--regenerate requires a KEY argument"
            REGEN_KEY="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            die "Unknown option: $1  (use --help for usage)"
            ;;
    esac
done

# ─── repo root detection ─────────────────────────────────────────────────────
# Support running from any working directory.
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

ROOT_EXAMPLE="${REPO_ROOT}/.env.example"
ROOT_ENV="${REPO_ROOT}/.env"
SUPA_EXAMPLE="${REPO_ROOT}/supabase/.env.example"
SUPA_ENV="${REPO_ROOT}/supabase/.env"

[ -f "$ROOT_EXAMPLE" ] || die "Cannot find $ROOT_EXAMPLE — are you in the repo root?"
[ -f "$SUPA_EXAMPLE" ] || die "Cannot find $SUPA_EXAMPLE — are you in the repo root?"

# ─── --regenerate mode ───────────────────────────────────────────────────────
if [ -n "$REGEN_KEY" ]; then
    info "Regenerating $REGEN_KEY ..."
    # Try both files
    found="no"
    if grep -q "^${REGEN_KEY}=" "$ROOT_ENV" 2>/dev/null; then
        regen_in_file "$ROOT_ENV" "$REGEN_KEY"
        found="yes"
    fi
    if grep -q "^${REGEN_KEY}=" "$SUPA_ENV" 2>/dev/null; then
        regen_in_file "$SUPA_ENV" "$REGEN_KEY"
        found="yes"
    fi
    [ "$found" = "yes" ] || die "$REGEN_KEY not found in $ROOT_ENV or $SUPA_ENV"
    exit 0
fi

# ─── normal setup mode ───────────────────────────────────────────────────────
printf "\n${BOLD}AgentSentinel — environment setup${RESET}\n\n"

# Root .env
if [ -f "$ROOT_ENV" ] && [ "$FORCE" = "no" ] && [ "$DRY_RUN" = "no" ]; then
    warn "$ROOT_ENV already exists — skipping (use --force to overwrite)"
else
    info "Processing $ROOT_EXAMPLE → $ROOT_ENV"
    process_file "$ROOT_EXAMPLE" "$ROOT_ENV" "$DRY_RUN" ""
    [ "$DRY_RUN" = "yes" ] || success "Wrote $ROOT_ENV"
fi

printf "\n"

# Supabase .env
if [ -f "$SUPA_ENV" ] && [ "$FORCE" = "no" ] && [ "$DRY_RUN" = "no" ]; then
    warn "$SUPA_ENV already exists — skipping (use --force to overwrite)"
else
    info "Processing $SUPA_EXAMPLE → $SUPA_ENV"
    process_file "$SUPA_EXAMPLE" "$SUPA_ENV" "$DRY_RUN" ""
    [ "$DRY_RUN" = "yes" ] || success "Wrote $SUPA_ENV"
fi

printf "\n"
info "Next steps:"
printf "  1. Fill in the ${YELLOW}⚠ Manual${RESET} entries above (Stripe keys, Supabase URL, etc.)\n"
printf "  2. Run ${BOLD}agentsentinel-config-check${RESET} to validate all required variables\n"
printf "  3. Run ${BOLD}agentsentinel-dashboard${RESET} to start the admin dashboard\n"
printf "  4. Run ${BOLD}supabase secrets set --env-file supabase/.env${RESET} to push secrets to Supabase\n\n"
