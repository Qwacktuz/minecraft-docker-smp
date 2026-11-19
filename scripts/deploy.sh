#!/usr/bin/env bash
set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
SERVICE=minecraft-service
ENV_FILE=$(mktemp "$APP_DIR/.env.XXXXXX")
trap 'rm -f -- "$ENV_FILE"' EXIT

echo "Preparing runtime configuration..."
sops --decrypt --output-type dotenv secrets/app.enc.env > "$ENV_FILE"
if [[ ! -s "$ENV_FILE" ]]; then
  echo "ERROR: SOPS produced an empty environment file." >&2
  exit 1
fi

compose=(docker compose --env-file "$ENV_FILE")
"${compose[@]}" config --quiet

echo "Pulling images before interrupting the server..."
"${compose[@]}" pull

running_services=$("${compose[@]}" ps --services --filter status=running)
if grep -Fxq "$SERVICE" <<< "$running_services"; then
  "${compose[@]}" exec -T "$SERVICE" rcon-cli "say System update in 5 seconds..." || true
  "${compose[@]}" exec -T "$SERVICE" rcon-cli "save-all flush"
  sleep 5
fi

# Keep the previous environment intact until validation and image pulls succeed.
mv -f -- "$ENV_FILE" .env
compose=(docker compose)

# RESTORE=latest replaces the local world with the newest R2 snapshot. It runs
# before `up`, so the backup container can never upload an empty world first.
if [[ "${RESTORE:-}" == latest ]]; then
  "${compose[@]}" stop minecraft-service backup
  restic() {
    # shellcheck disable=SC1091
    (set -a; . ./.env; set +a
     RESTIC_REPOSITORY="s3:${R2_ENDPOINT}/${R2_BUCKET_NAME}"
     AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
     export RESTIC_REPOSITORY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
     # -e NAME (without a value) keeps secrets out of the process arguments.
     docker run --rm --entrypoint restic -v "$APP_DIR/data/minecraft:/data" \
       -e RESTIC_REPOSITORY -e RESTIC_PASSWORD -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
       itzg/mc-backup -o s3.region=auto "$@")
  }
  if [[ "${NEW_WORLD:-}" == 1 ]]; then
    echo "NEW_WORLD=1: starting without restoring a snapshot."
  elif ! restic snapshots --json --latest 1 | grep -q '"id"'; then
    echo "ERROR: No R2 snapshot found. Use NEW_WORLD=1 to create a fresh world." >&2
    exit 1
  else
    echo "Restoring the latest R2 snapshot (old data kept in data/minecraft.previous)..."
    mkdir -p data
    docker run --rm -v "$APP_DIR/data:/d" alpine sh -c \
      'rm -rf /d/minecraft.previous; if [ -d /d/minecraft ]; then mv /d/minecraft /d/minecraft.previous; fi; mkdir -p /d/minecraft'
    restic restore latest --target /
    docker run --rm -v "$APP_DIR/data/minecraft:/data" alpine chown -R 1000:1000 /data
  fi
fi

# Never start without a world: Minecraft would generate a new one and the backup
# container would upload it over the real one's "latest".
if [[ ! -f data/minecraft/world/level.dat && "${NEW_WORLD:-}" != 1 ]]; then
  echo "ERROR: No world in data/minecraft. Use RESTORE=latest, or NEW_WORLD=1 for a fresh world." >&2
  exit 1
fi

echo "Updating containers and waiting for health checks..."
if ! "${compose[@]}" up -d --remove-orphans --wait --wait-timeout 600; then
  "${compose[@]}" ps >&2 || true
  echo "ERROR: Deployment did not become healthy. Inspect docker compose logs." >&2
  exit 1
fi

"${compose[@]}" exec -T "$SERVICE" rcon-cli "say Deployment complete." || true
echo "Deployment completed; Minecraft health check passed."
