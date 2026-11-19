#!/usr/bin/env bash
# Undoes the last scripts/restore-backup.sh: puts the newest
# data/minecraft_pre_restore_* back as the world. Run on the app host.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/app}"
cd "$APP_DIR"
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"

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
fix_owner
docker compose up -d --wait --wait-timeout 600 minecraft-service
echo "Rolled back to data/$previous."
