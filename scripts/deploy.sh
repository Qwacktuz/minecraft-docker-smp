#!/usr/bin/env bash
set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
SERVICE=minecraft-service
ENV_FILE=$(mktemp "$APP_DIR/.env.XXXXXX")
trap 'rm -f -- "$ENV_FILE"' EXIT

echo "Preparing runtime configuration..."
sops --decrypt --output-type dotenv secrets/secrets.enc.env > "$ENV_FILE"
if [[ ! -s "$ENV_FILE" ]]; then
  echo "ERROR: SOPS produced an empty environment file." >&2
  exit 1
fi

TS_IP=$(tailscale ip -4)
if [[ ! "$TS_IP" =~ ^100\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] ||
  (( 10#${BASH_REMATCH[1]} < 64 || 10#${BASH_REMATCH[1]} > 127 ||
     10#${BASH_REMATCH[2]} > 255 || 10#${BASH_REMATCH[3]} > 255 )); then
  echo "ERROR: Tailscale did not return one valid tailnet IPv4 address." >&2
  exit 1
fi
export TS_IP
printf '\nTS_IP=%s\n' "$TS_IP" >> "$ENV_FILE"

compose=(docker compose --env-file "$ENV_FILE")
"${compose[@]}" config --quiet

# Older releases stored Loki data in the container's /tmp/loki directory.
loki_id=$("${compose[@]}" ps --all --quiet loki)
if [[ -n "$loki_id" && ! -f .loki-storage-migrated ]]; then
  loki_config_mount=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/loki/local-config.yaml"}}{{.Type}}{{end}}{{end}}' "$loki_id")
  if [[ "$loki_config_mount" != bind ]]; then
    echo "ERROR: Preserve existing Loki data before deployment; see docs/loki-migration.md." >&2
    exit 1
  fi
fi

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
echo "Updating containers and waiting for health checks..."
if ! "${compose[@]}" up -d --remove-orphans --wait --wait-timeout 600; then
  "${compose[@]}" ps >&2 || true
  echo "ERROR: Deployment did not become healthy. Inspect docker compose logs." >&2
  exit 1
fi

"${compose[@]}" exec -T "$SERVICE" rcon-cli "say Deployment complete." || true
echo "Deployment completed; Minecraft health check passed."
