#!/bin/bash
set -euo pipefail

APP_DIR="$HOME/app"

# Ensure we are in the correct directory
cd "$APP_DIR" || exit 1

echo "running rollback..."
echo "🔍 Searching for local pre-restore backups..."

# 1. Find the latest backup directory (Using a container because host user might not have permission to ls subfolders)
LATEST_BACKUP=$(docker run --rm -v "$(pwd)/data:/host_data" alpine sh -c "ls -1d /host_data/minecraft_pre_restore_* 2>/dev/null | sort -r | head -n 1")

if [ -z "$LATEST_BACKUP" ]; then
  echo "❌ No local backups found (data/minecraft_pre_restore_*)."
  exit 1
fi

# Clean up path from container perspective to host perspective
LATEST_BACKUP=$(echo "$LATEST_BACKUP" | sed 's|/host_data/|data/|')
echo "⚠️  FOUND BACKUP: $LATEST_BACKUP"
echo "------------------------------------------------------------"
echo "This will:"
echo "  1. DELETE the current 'data/minecraft' folder (the broken restore)."
echo "  2. MOVE '$LATEST_BACKUP' back to 'data/minecraft'."
echo "  3. Restart the server."
echo "------------------------------------------------------------"
echo ""

read -r -p "🚨 Are you sure you want to ROLLBACK to this state? [y/N]: " confirm
if [[ ! $confirm =~ ^[yY] ]]; then
  echo "❌ Aborted."
  exit 0
fi

# 2. Stop the Server
echo "🛑 Stopping Minecraft Server..."
docker compose stop minecraft-service

# 3. Swap the folders
echo "🗑️  Removing broken data/minecraft folder and restoring $LATEST_BACKUP..."

# Use a container to perform the swap (host user lacks permission for Docker root volumes)
docker run --rm \
  -v "$(pwd)/data:/host_data" \
  alpine sh -c "rm -rf /host_data/minecraft && mv /host_data/$(basename "$LATEST_BACKUP") /host_data/minecraft"

# 4. Fix Permissions (Just in case)
echo "🔧 Ensuring permissions are correct..."
# Force ownership to internal uid 1000 (External 100999)
docker run --rm -v "$(pwd)/data/minecraft:/data" alpine chown -R 1000:1000 /data

# 5. Restart
echo "🚀 Starting Minecraft Server..."
docker compose up -d minecraft-service

echo "✅ Rollback Complete!"
echo "   Server restored to state before the last restore attempt."
echo "   Monitoring logs for 10 seconds..."
timeout 20s docker compose logs -f minecraft-service || true
