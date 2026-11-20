#!/usr/bin/env bash
# Publishes the backup list for the web app (web/) as backups.json: snapshot
# IDs, times and tags, no world data. Runs on the VPS from ~/app; `bin/server`
# calls it after start and after the final backup on stop. A Worker can't run
# restic, so the VPS writes this for it. Does nothing unless WEB_BUCKET is set
# in secrets/app.enc.env.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
OUT=.cache/status

die() { echo "publish-status: $*" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
. ./.env
set +a
if [[ -z "${WEB_BUCKET:-}" ]]; then
  echo "WEB_BUCKET is not set; not publishing backups.json."
  exit 0
fi

mkdir -p "$OUT"
trap 'rm -rf -- "$OUT"' EXIT
restic --no-lock snapshots --host "$WORLD_HOST" --json |
  python3 scripts/snapshots.py --json > "$OUT/backups.json" ||
  die "could not list the snapshots"

r2_rclone "$(id -u):$(id -g)" "$APP_DIR/$OUT:/upload:ro" \
  copyto /upload/backups.json "r2:$WEB_BUCKET/backups.json"
echo "Published backups.json to $WEB_BUCKET."
