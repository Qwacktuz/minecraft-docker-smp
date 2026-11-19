#!/usr/bin/env bash
# Checks the backup repository: structure plus a sample of the data, the
# snapshot list, and the size of the newest snapshot. Run on the app host.
#
#   bash scripts/test-backup.sh [percent-of-data-to-read]   (default 5%)
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/app}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
[[ -f .env ]] || { echo "Missing $APP_DIR/.env; run a deploy first." >&2; exit 1; }

echo "Checking the repository and reading ${1:-5}% of the data..."
restic check --read-data-subset "${1:-5}%"
restic --no-lock snapshots --host "$WORLD_HOST"
restic --no-lock stats latest --host "$WORLD_HOST"
echo "Backup check passed."
