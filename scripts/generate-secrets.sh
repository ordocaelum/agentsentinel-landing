#!/bin/sh
# scripts/generate-secrets.sh
#
# Convenience alias for scripts/setup-env.sh
# Generates cryptographically secure secrets and scaffolds .env files.
#
# Usage:
#   ./scripts/generate-secrets.sh              # create .env files from templates
#   ./scripts/generate-secrets.sh --force      # overwrite existing .env files
#   ./scripts/generate-secrets.sh --dry-run    # print what would be written
#   ./scripts/generate-secrets.sh --regenerate KEY  # rotate a single secret
#
# See scripts/setup-env.sh for full documentation.

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
exec "${SCRIPT_DIR}/setup-env.sh" "$@"
