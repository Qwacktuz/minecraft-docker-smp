#!/usr/bin/env bash
# Publishes what the web app (web/) can't find out itself, to the private
# WEB_BUCKET. Runs on the VPS from ~/app; `bin/server` calls it after start and
# after the final backup on stop. Does nothing unless WEB_BUCKET is set in
# secrets/app.enc.env.
#
# - backups.json: snapshot IDs, times and tags, no world data (a Worker can't
#   run restic).
# - players.json: the whitelist with op flags (scripts/web_status.py players).
# - leaderboard.json: each whitelisted player's totals for the public
#   leaderboards (scripts/leaderboard.py): playtime, distance, blocks mined
#   and placed... At a stop it has the whole session.
# - vps.json, only when bin/server passes SERVER_TYPE, SERVER_LOCATION and
#   SERVER_IPV4 (at start): the server type and the machine's hardware.
#
# Only the backup list is required; the others only warn when they fail.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
OUT=.cache/status

die() { echo "publish-status: $*" >&2; exit 1; }
warn() { echo "publish-status: warning: $*" >&2; }

set -a
# shellcheck disable=SC1091
. ./.env
set +a
if [[ -z "${WEB_BUCKET:-}" ]]; then
  echo "WEB_BUCKET is not set; not publishing the status for the web app."
  exit 0
fi

rm -rf -- "$OUT"
mkdir -p "$OUT"
trap 'rm -rf -- "$OUT"' EXIT
restic --no-lock snapshots --host "$WORLD_HOST" --json |
  python3 scripts/snapshots.py --json > "$OUT/backups.json" ||
  die "could not list the snapshots"

python3 scripts/web_status.py players data/minecraft > "$OUT/players.json" ||
  { rm -f "$OUT/players.json"; warn "could not read the whitelist; players.json not updated"; }

python3 scripts/leaderboard.py data/minecraft > "$OUT/leaderboard.json" ||
  { rm -f "$OUT/leaderboard.json"; warn "could not read the player stats; leaderboard.json not updated"; }

if [[ -n "${SERVER_TYPE:-}" ]]; then
  python3 scripts/web_status.py vps "$SERVER_TYPE" "${SERVER_LOCATION:-}" "${SERVER_IPV4:-}" > "$OUT/vps.json" ||
    { rm -f "$OUT/vps.json"; warn "could not describe the VPS; vps.json not updated"; }
fi

# copy, not sync: a file that wasn't written this time keeps its last version.
r2_rclone "$(id -u):$(id -g)" "$APP_DIR/$OUT:/upload:ro" copy /upload "r2:$WEB_BUCKET"
echo "Published $(cd "$OUT" && echo *.json) to $WEB_BUCKET."
