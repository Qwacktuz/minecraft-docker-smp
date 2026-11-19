#!/usr/bin/env bash
# Publishes the world as a public download, world.zip, without player data.
# Runs on the VPS from ~/app with the game stopped; `bin/server stop` calls it
# after the final backup. Does nothing unless PUBLIC_WORLD_BUCKET is set in
# secrets/app.enc.env.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
RCLONE_IMAGE=rclone/rclone:1.75.2
WORLD=data/minecraft/world
ZIP=.cache/world.zip

die() { echo "publish-world: $*" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
. ./.env
set +a
if [[ -z "${PUBLIC_WORLD_BUCKET:-}" ]]; then
  echo "PUBLIC_WORLD_BUCKET is not set; not publishing world.zip."
  exit 0
fi
[[ -f "$WORLD/level.dat" ]] || die "no world in $WORLD"
if docker compose ps --status running --services 2>/dev/null | grep -qx minecraft-service; then
  die "the game is running; stop it first so the files are consistent"
fi

mkdir -p .cache
trap 'rm -f -- "$ZIP" "$ZIP.tmp"' EXIT
python3 scripts/world_zip.py "$WORLD" "$ZIP.tmp"
mv -- "$ZIP.tmp" "$ZIP"

# Uses the backup bucket's R2 credentials. -e NAME keeps the values out of argv.
export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT" RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
# R2 swaps the object in only once the upload completes, so downloads never
# see a partial file.
docker run --rm --user "$(id -u):$(id -g)" -v "$APP_DIR/.cache:/upload:ro" \
  -e RCLONE_CONFIG_R2_TYPE -e RCLONE_CONFIG_R2_PROVIDER -e RCLONE_CONFIG_R2_ACCESS_KEY_ID \
  -e RCLONE_CONFIG_R2_SECRET_ACCESS_KEY -e RCLONE_CONFIG_R2_ENDPOINT -e RCLONE_CONFIG_R2_NO_CHECK_BUCKET \
  "$RCLONE_IMAGE" copyto /upload/world.zip "r2:$PUBLIC_WORLD_BUCKET/world.zip" \
  --header-upload "Cache-Control: no-cache" --s3-chunk-size 64M
echo "Published world.zip to $PUBLIC_WORLD_BUCKET."
