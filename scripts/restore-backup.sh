#!/usr/bin/env bash
# Restores the whole world from a chosen snapshot. Run on the app host:
#
#   bash scripts/restore-backup.sh [snapshot-id|latest] [--yes]
#
# The current world is moved to data/minecraft_pre_restore_<time> first;
# scripts/rollback-backup.sh puts it back.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/app}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
[[ -f .env ]] || { echo "Missing $APP_DIR/.env; run a deploy first." >&2; exit 1; }

snapshot=${1:-}
if [[ -z "$snapshot" ]]; then
  restic --no-lock snapshots --host "$WORLD_HOST"
  read -r -p "Snapshot ID to restore (or 'latest'): " snapshot
fi
[[ -n "$snapshot" ]] || { echo "No snapshot given." >&2; exit 1; }
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
fix_owner
docker compose up -d --wait --wait-timeout 600 minecraft-service
echo "Restored. The previous world is in data/$aside."
