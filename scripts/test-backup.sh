#!/usr/bin/env bash
# Checks the backup repository: structure plus a sample of the data, the
# snapshot list, and the size of the newest snapshot. Runs on the app host, or
# on the laptop through `bin/server check` (which decrypts the credentials).
#
#   bash scripts/test-backup.sh [percent-of-data-to-read]   (default 5%)
#
# RESTIC_NO_LOCK=1 checks without locking the repository, so nothing is written
# to it (bin/server check sets it: the laptop never writes to R2, and an
# exclusive lock would make a running VPS's backups fail meanwhile).
# RESTIC_SOURCE=vault checks the vault bucket instead (see lib.sh).
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/app}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
[[ -f .env || -n "${R2_ENDPOINT:-}" ]] || { echo "Missing $APP_DIR/.env; run a deploy first." >&2; exit 1; }
percent=${1:-5}
if ! [[ "$percent" =~ ^[0-9]+(\.[0-9]+)?$ ]] || ! awk -v p="$percent" 'BEGIN { exit !(p > 0 && p <= 100) }'; then
  echo "The percentage must be a number between 0 and 100, not '$percent'." >&2
  exit 2
fi
lock=()
[[ "${RESTIC_NO_LOCK:-}" == 1 ]] && lock=(--no-lock)

echo "Checking the repository and reading ${percent}% of the data..."
restic ${lock[@]+"${lock[@]}"} check --read-data-subset "${percent}%"
restic --no-lock snapshots --host "$WORLD_HOST"
restic --no-lock stats latest --host "$WORLD_HOST"
echo "Backup check passed."
