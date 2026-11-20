#!/usr/bin/env bash
# Publishes the world as a public download, world.zip, without player data.
# Runs on the VPS from ~/app with the game stopped; `bin/server stop` calls it
# after the final backup. Does nothing unless PUBLIC_WORLD_BUCKET is set in
# secrets/app.enc.env.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
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

# R2 swaps the object in only once the upload completes, so downloads never
# see a partial file.
r2_rclone "$(id -u):$(id -g)" "$APP_DIR/.cache:/upload:ro" \
  copyto /upload/world.zip "r2:$PUBLIC_WORLD_BUCKET/world.zip" \
  --header-upload "Cache-Control: no-cache" --s3-chunk-size 64M
echo "Published world.zip to $PUBLIC_WORLD_BUCKET."
