#!/usr/bin/env bash
# Restores single region files from a snapshot, e.g. to undo a prune in one area.
# Run on the VPS from ~/app. Paths are relative to data/minecraft:
#
#   bash scripts/restore-regions.sh <snapshot-id> world/dimensions/minecraft/overworld/region/r.2.-1.mca ...
#
# For each region file, the matching entities/ and poi/ files are restored too.
# The game is stopped meanwhile. Changes made in those regions since the
# snapshot are lost; everything else is untouched.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/app}"
cd "$APP_DIR"
(( $# >= 2 )) || { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
snapshot=$1; shift

includes=()
for path in "$@"; do
  [[ "$path" =~ ^(world/.+/)(region|entities|poi)/(r\.-?[0-9]+\.-?[0-9]+\.mca)$ ]] ||
    { echo "not a region file path: $path" >&2; exit 2; }
  for kind in region entities poi; do
    includes+=(--include "/data/${BASH_REMATCH[1]}$kind/${BASH_REMATCH[3]}")
  done
done

docker compose stop minecraft-service
# -e NAME (without a value) keeps the secrets out of the process arguments.
# shellcheck disable=SC1091
(set -a; . ./.env; set +a
 RESTIC_REPOSITORY="s3:${R2_ENDPOINT}/${R2_BUCKET_NAME}"
 AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
 export RESTIC_REPOSITORY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
 docker run --rm --entrypoint restic -v "$APP_DIR/data/minecraft:/data" \
   -e RESTIC_REPOSITORY -e RESTIC_PASSWORD -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
   itzg/mc-backup --no-lock -o s3.region=auto restore "$snapshot" --target / "${includes[@]}")
docker run --rm -v "$APP_DIR/data/minecraft:/data" alpine chown -R 1000:1000 /data
docker compose up -d --wait --wait-timeout 600 minecraft-service
echo "Restored $# region file(s) from ${snapshot:0:8}."
