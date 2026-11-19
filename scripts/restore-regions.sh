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
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
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
restic --no-lock restore "$snapshot" --target / "${includes[@]}"
fix_owner
docker compose up -d --wait --wait-timeout 600 minecraft-service
echo "Restored $# region file(s) from ${snapshot:0:8}."
