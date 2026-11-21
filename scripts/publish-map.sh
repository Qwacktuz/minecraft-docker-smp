#!/usr/bin/env bash
# Publishes BlueMap's web map as static files to the public world bucket, under
# map/ (https://world.cactuz.dev/map/), so the map stays online while the VPS
# is gone. Runs on the VPS from ~/app with the game stopped; `bin/server stop`
# calls it after publish-world.sh, and deploy.sh pulls the files back after a
# restore so BlueMap only renders what changed. Does nothing unless
# PUBLIC_WORLD_BUCKET is set in secrets/app.enc.env. See docs/map.md.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"

die() { echo "publish-map: $*" >&2; exit 1; }

set -a
# shellcheck disable=SC1091
. ./.env
set +a
if [[ -z "${PUBLIC_WORLD_BUCKET:-}" ]]; then
  echo "PUBLIC_WORLD_BUCKET is not set; not publishing the map."
  exit 0
fi
if [[ ! -f "$MAP_WEB/index.html" || ! -f "$MAP_WEB/settings.json" ]]; then
  echo "BlueMap has not written its web app ($MAP_WEB); no map to publish."
  exit 0
fi
if docker compose ps --status running --services 2>/dev/null | grep -qx minecraft-service; then
  die "the game is running; stop it first so the tiles and render state agree"
fi

# copy, not sync: it never deletes, so a map that is still re-rendering after a
# failed pull can't wipe the published one. The tiles stay .gz files; the web
# app decompresses them itself (client-decompression in webapp.conf), so no
# Content-Encoding header is set. The render state (maps/*/rstate) goes too:
# deploy.sh pulls it back, so the next VPS only renders what changed.
r2_rclone "$(id -u):$(id -g)" "$APP_DIR/$MAP_WEB:/work:ro" \
  copy /work "r2:$PUBLIC_WORLD_BUCKET/$MAP_PREFIX" \
  --exclude sql.php --exclude "*.js.map" \
  --checksum --fast-list --transfers 32 --stats-one-line --stats 1m \
  --header-upload "Cache-Control: public, max-age=300"
echo "Published the map to $PUBLIC_WORLD_BUCKET/$MAP_PREFIX/."

# The same files as one archive, which deploy.sh downloads in one go (the
# tiles are .gz already, so it isn't compressed again). If it can't be
# replaced, the old one is deleted: deploy.sh then pulls the files instead of
# an older map.
mkdir -p .cache
archive_ok=0
if docker run --rm --user "$(id -u):$(id -g)" -v "$APP_DIR/$MAP_WEB:/work:ro" -v "$APP_DIR/.cache:/out" \
     "$ALPINE_IMAGE" tar -C /work --exclude sql.php --exclude "*.js.map" -cf "/out/$MAP_ARCHIVE" . &&
   r2_rclone "$(id -u):$(id -g)" "$APP_DIR/.cache:/work:ro" \
     copyto "/work/$MAP_ARCHIVE" "r2:$PUBLIC_WORLD_BUCKET/$MAP_ARCHIVE" --stats-one-line --stats 1m; then
  archive_ok=1
  echo "Published the map archive ($MAP_ARCHIVE)."
fi
rm -f ".cache/$MAP_ARCHIVE"
if (( archive_ok == 0 )); then
  r2_rclone root "$APP_DIR/.cache:/work:ro" deletefile "r2:$PUBLIC_WORLD_BUCKET/$MAP_ARCHIVE" >/dev/null 2>&1 || true
  die "could not publish the map archive; the files in $MAP_PREFIX/ are published"
fi
