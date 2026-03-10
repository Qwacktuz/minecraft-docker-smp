#!/bin/bash
set -euo pipefail

APP_DIR="$HOME/app"
SNAP_ID="${1:-}" # Optional: Pass snapshot ID as first argument

cd "$APP_DIR" || exit 1

if [ ! -f ".env" ]; then
  echo "❌ Missing $APP_DIR/.env. Run deploy to generate it."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source ".env"
set +a

echo "⚠️  --- MINECRAFT RESTORE SCRIPT ---"

# 1. Select Snapshot if not provided
if [ -z "$SNAP_ID" ]; then
  echo "📋 Fetching available snapshots from Cloudflare R2..."
  # Use standalone container to avoid compose :ro restrictions
  docker run --rm \
    --entrypoint restic \
    -e "RESTIC_REPOSITORY=s3:${R2_ENDPOINT}/${R2_BUCKET_NAME}" \
    -e "RESTIC_PASSWORD=${RESTIC_PASSWORD}" \
    -e "AWS_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}" \
    -e "AWS_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}" \
    -e "RESTIC_OPTS=-o s3.connections=10 -o s3.region=auto --compression auto" \
    itzg/mc-backup \
    snapshots
  echo ""
  read -r -p "Enter Snapshot ID to restore (or type 'latest'): " SNAP_ID
fi

if [ -z "$SNAP_ID" ]; then
  echo "❌ No ID entered. Exiting."
  exit 1
fi

# Skip confirmation if '--latest' or '--yes' is passed as the second argument
SKIP_CONFIRM="${2:-}"
if [[ "$SKIP_CONFIRM" != "--yes" && "$SKIP_CONFIRM" != "-y" ]]; then
  read -r -p "Are you sure you want to overwrite production data with snapshot '$SNAP_ID'? [y/N]: " confirm
  if [[ ! $confirm =~ ^[yY] ]]; then
    echo "❌ Aborted."
    exit 0
  fi
fi

# 2. Stop Server
echo "🛑 Stopping Minecraft Server..."
docker compose stop minecraft-service

# 3. Safety Swap (Backup current state before overwrite)
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
BACKUP_DIR="data/minecraft_pre_restore_$TIMESTAMP"
echo "📦 Moving current data to '$BACKUP_DIR'..."

# Use a container to perform the move (since host user can't move root-owned Docker files)
if [ -d "data/minecraft" ]; then
  docker run --rm \
    -v "$(pwd)/data:/host_data" \
    alpine sh -c "mv /host_data/minecraft /host_data/minecraft_pre_restore_$TIMESTAMP && mkdir -p /host_data/minecraft"
else
  mkdir -p data/minecraft
fi

# 4. Restore
echo "📥 Restoring data from restic snapshot '$SNAP_ID'..."
# Use manual 'docker run' to ensure read-write access (bypassing compose service :ro)
docker run --rm \
  --entrypoint restic \
  -v "$(pwd)/data/minecraft:/data" \
  -e "RESTIC_REPOSITORY=s3:${R2_ENDPOINT}/${R2_BUCKET_NAME}" \
  -e "RESTIC_PASSWORD=${RESTIC_PASSWORD}" \
  -e "AWS_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}" \
  -e "AWS_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}" \
  -e "RESTIC_OPTS=-o s3.connections=10 -o s3.region=auto --compression auto" \
  itzg/mc-backup \
  restore "$SNAP_ID" --target /

# 5. Fix permissions
echo "🔧 Fixing permissions for UID 1000 (Minecraft default)..."
docker run --rm -v "$(pwd)/data/minecraft:/data" alpine chown -R 1000:1000 /data

# 6. Restart
echo "🚀 Starting Minecraft Server..."
docker compose up -d minecraft-service

echo "✅ Restore Complete!"
echo "Old data saved at: data/minecraft_pre_restore_$TIMESTAMP"
echo "Monitoring logs for 20 seconds..."
timeout 20s docker compose logs -f minecraft-service || true
