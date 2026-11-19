#!/usr/bin/env bash
# Restores the world from the backups. Run on the app host from ~/app:
#
#   bash scripts/restore.sh world [snapshot-id|latest] [--yes]
#       Restores the whole world. The current one is moved aside to
#       data/minecraft_pre_restore_<time> first.
#   bash scripts/restore.sh regions <snapshot-id> <path>...
#       Restores single region files, e.g. to undo a prune in one area. Paths
#       are relative to data/minecraft, e.g.
#       world/dimensions/minecraft/overworld/region/r.2.-1.mca. The matching
#       entities/ and poi/ files are restored too. Changes made in those regions
#       since the snapshot are lost; everything else is untouched.
#   bash scripts/restore.sh rollback
#       Undoes the last `world` restore: puts the newest
#       data/minecraft_pre_restore_* back as the world.
#
# The game is stopped meanwhile.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/app}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
# The full ID of a WORLD_HOST snapshot; stops for any other snapshot.
resolve() {
  world_snapshot "$1" ||
    { echo "No single $WORLD_HOST snapshot matches '$1' (restores only use the VPS backups)." >&2; exit 1; }
}
restart() {
  fix_owner
  docker compose up -d --wait --wait-timeout 600 minecraft-service
}

world() {
  [[ -f .env ]] || { echo "Missing $APP_DIR/.env; run a deploy first." >&2; exit 1; }
  local snapshot=${1:-} confirm aside
  if [[ -z "$snapshot" ]]; then
    restic --no-lock snapshots --host "$WORLD_HOST"
    read -r -p "Snapshot ID to restore (or 'latest'): " snapshot
  fi
  [[ -n "$snapshot" ]] || { echo "No snapshot given." >&2; exit 1; }
  snapshot=$(resolve "$snapshot")
  if [[ "${2:-}" != --yes && "${2:-}" != -y ]]; then
    read -r -p "Replace the current world with snapshot '$snapshot'? [y/N] " confirm
    [[ "$confirm" =~ ^[yY] ]] || { echo "Aborted."; exit 0; }
  fi

  docker compose stop minecraft-service
  aside=minecraft_pre_restore_$(date +%Y%m%d-%H%M%S)
  echo "Moving the current world to data/$aside..."
  docker run --rm -v "$APP_DIR/data:/d" "$ALPINE_IMAGE" sh -c \
    "if [ -d /d/minecraft ]; then mv /d/minecraft /d/$aside; fi; mkdir -p /d/minecraft"
  echo "Restoring snapshot $snapshot..."
  restic --no-lock restore "$snapshot" --host "$WORLD_HOST" --target /
  restart
  echo "Restored. The previous world is in data/$aside."
}

regions() {
  (( $# >= 2 )) || usage
  local snapshot=$1 path kind includes=()
  shift
  for path in "$@"; do
    [[ "$path" =~ ^(world/.+/)(region|entities|poi)/(r\.-?[0-9]+\.-?[0-9]+\.mca)$ ]] ||
      { echo "not a region file path: $path" >&2; exit 2; }
    for kind in region entities poi; do
      includes+=(--include "/data/${BASH_REMATCH[1]}$kind/${BASH_REMATCH[3]}")
    done
  done
  snapshot=$(resolve "$snapshot")

  docker compose stop minecraft-service
  restic --no-lock restore "$snapshot" --target / "${includes[@]}"
  restart
  echo "Restored $# region file(s) from ${snapshot:0:8}."
}

rollback() {
  local previous confirm
  previous=$(docker run --rm -v "$APP_DIR/data:/d" "$ALPINE_IMAGE" sh -c \
    'ls -1d /d/minecraft_pre_restore_* 2>/dev/null | sort -r | head -n 1')
  [[ -n "$previous" ]] || { echo "No data/minecraft_pre_restore_* found." >&2; exit 1; }
  previous=$(basename "$previous")

  echo "This deletes data/minecraft and puts data/$previous back in its place."
  read -r -p "Roll back? [y/N] " confirm
  [[ "$confirm" =~ ^[yY] ]] || { echo "Aborted."; exit 0; }

  docker compose stop minecraft-service
  docker run --rm -v "$APP_DIR/data:/d" "$ALPINE_IMAGE" sh -c \
    "rm -rf /d/minecraft && mv /d/$previous /d/minecraft"
  restart
  echo "Rolled back to data/$previous."
}

case "${1:-}" in
  world | regions | rollback) command=$1; shift; "$command" "$@" ;;
  *) usage ;;
esac
