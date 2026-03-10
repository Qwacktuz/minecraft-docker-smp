#!/bin/bash
set -euo pipefail

APP_DIR="$HOME/app"

cd "$APP_DIR" || exit 1

if [ ! -f ".env" ]; then
  echo "❌ Missing $APP_DIR/.env. Run deploy to generate it."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source ".env"
set +a

echo "🔎 Running restic integrity check..."
docker run --rm \
  --entrypoint restic \
  -v "$(pwd)/data/minecraft:/data:ro" \
  -e "RESTIC_REPOSITORY=s3:${R2_ENDPOINT}/${R2_BUCKET_NAME}" \
  -e "RESTIC_PASSWORD=${RESTIC_PASSWORD}" \
  -e "AWS_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}" \
  -e "AWS_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}" \
  -e "RESTIC_OPTS=-o s3.connections=10 -o s3.region=auto --compression auto" \
  itzg/mc-backup \
  check

echo ""
echo "📸 Listing all available snapshots..."
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
echo "📊 Snapshot stats for 'latest'..."
docker run --rm \
  --entrypoint restic \
  -e "RESTIC_REPOSITORY=s3:${R2_ENDPOINT}/${R2_BUCKET_NAME}" \
  -e "RESTIC_PASSWORD=${RESTIC_PASSWORD}" \
  -e "AWS_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}" \
  -e "AWS_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}" \
  -e "RESTIC_OPTS=-o s3.connections=10 -o s3.region=auto --compression auto" \
  itzg/mc-backup \
  stats latest

echo ""
echo "✅ Backup test complete!"
