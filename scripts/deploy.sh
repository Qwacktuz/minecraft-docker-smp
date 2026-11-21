#!/usr/bin/env bash
set -euo pipefail
umask 077

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"
SERVICE=minecraft-service
# shellcheck source=lib.sh
. "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
ENV_FILE=$(mktemp "$APP_DIR/.env.XXXXXX")
trap 'rm -f -- "$ENV_FILE"' EXIT

phase decrypt
echo "Preparing runtime configuration..."
sops --decrypt --output-type dotenv secrets/app.enc.env > "$ENV_FILE"
if [[ ! -s "$ENV_FILE" ]]; then
  echo "ERROR: SOPS produced an empty environment file." >&2
  exit 1
fi

# MeowIce's JIT flags crash the JVM's C2 compiler on ARM64 (e.g. Apple Silicon
# under OrbStack); use Aikar's conservative G1 flags there.
case "$(docker info --format '{{.Architecture}}')" in
  aarch64 | arm64) printf 'USE_MEOWICE_FLAGS=false\nUSE_AIKAR_FLAGS=true\n' >> "$ENV_FILE" ;;
esac

# Only the VPS backs up (BACKUPS=1). Anywhere else the world is a read-only
# copy: the backup service stays off, so nothing is ever written to R2.
if [[ "${BACKUPS:-}" == 1 ]]; then
  echo "COMPOSE_PROFILES=backup" >> "$ENV_FILE"
fi

# `map_pull <bucket>`: the map archive in one download, or, without one, the
# files one by one.
map_pull() {
  local web=/data/minecraft/${MAP_WEB#data/minecraft/}
  if r2_rclone root "$APP_DIR/data:/data" copyto "r2:$1/$MAP_ARCHIVE" "/data/$MAP_ARCHIVE" \
       --multi-thread-streams 8 --stats-one-line --stats 1m 2>/dev/null; then
    # shellcheck disable=SC2016 # expanded in the container
    if docker run --rm -v "$APP_DIR/data:/data" -e WEB="$web" -e ARCHIVE="/data/$MAP_ARCHIVE" "$ALPINE_IMAGE" \
         sh -c 'mkdir -p "$WEB" && tar -C "$WEB" -xf "$ARCHIVE"; status=$?; rm -f "$ARCHIVE"; exit $status'; then
      echo "Unpacked the map archive."
      return 0
    fi
    echo "warning: could not unpack the map archive; pulling the files instead" >&2
  fi
  r2_rclone root "$APP_DIR/data/minecraft:/data" \
    copy "r2:$1/$MAP_PREFIX" "/data/${MAP_WEB#data/minecraft/}" \
    --fast-list --transfers 32 --stats-one-line --stats 1m
}

compose=(docker compose --env-file "$ENV_FILE")
"${compose[@]}" config --quiet

phase image-pull
echo "Pulling images before interrupting the server..."
"${compose[@]}" pull

phase
running_services=$("${compose[@]}" ps --services --filter status=running)
if grep -Fxq "$SERVICE" <<< "$running_services"; then
  "${compose[@]}" exec -T "$SERVICE" rcon-cli "say System update in 5 seconds..." || true
  "${compose[@]}" exec -T "$SERVICE" rcon-cli "save-all flush"
  sleep 5
fi

# Keep the previous environment intact until validation and image pulls succeed.
mv -f -- "$ENV_FILE" .env
compose=(docker compose)
if [[ "${BACKUPS:-}" != 1 ]]; then
  # Without BACKUPS=1 nothing may back up: remove a backup container left behind.
  "${compose[@]}" --profile backup rm --stop --force backup >/dev/null 2>&1 || true
fi

# RESTORE=latest (or a snapshot ID) replaces the local world with that R2
# snapshot. It runs before `up`, so the backup container can never upload an
# empty world first. RESTIC_SOURCE=vault restores from the vault (lib.sh).
if [[ -n "${RESTORE:-}" ]]; then
  "${compose[@]}" stop
  # Read-only restic: --no-lock writes nothing to R2, and --host (or
  # world_snapshot for an explicit ID) limits it to the VPS snapshots.
  if [[ "${NEW_WORLD:-}" == 1 ]]; then
    echo "NEW_WORLD=1: starting without restoring a snapshot."
  elif ! restic --no-lock snapshots --host "$WORLD_HOST" --json --latest 1 | grep -q '"id"'; then
    echo "ERROR: No R2 snapshot found. Use NEW_WORLD=1 to create a fresh world." >&2
    exit 1
  else
    snapshot=latest
    if [[ "$RESTORE" != latest ]]; then
      snapshot=$(world_snapshot "$RESTORE") ||
        { echo "ERROR: No single $WORLD_HOST snapshot matches '$RESTORE'." >&2; exit 1; }
    fi
    echo "Restoring R2 snapshot $snapshot (old data kept in data/minecraft.previous)..."
    mkdir -p data
    docker run --rm -v "$APP_DIR/data:/d" "$ALPINE_IMAGE" sh -c \
      'rm -rf /d/minecraft.previous; if [ -d /d/minecraft ]; then mv /d/minecraft /d/minecraft.previous; fi; mkdir -p /d/minecraft'
    # The world and the map run side by side: the backups exclude bluemap/, so
    # they never write the same files.
    timed restic-restore restic --no-lock restore "$snapshot" --host "$WORLD_HOST" --target / &
    restore_job=$!
    # BlueMap's tiles and render state aren't in the backups; they live in the
    # public bucket (scripts/publish-map.sh). Without them BlueMap renders the
    # whole world again, so a failed pull only warns.
    # shellcheck disable=SC1091
    public_bucket=$(set -a; . ./.env; echo "${PUBLIC_WORLD_BUCKET:-}")
    map_job=
    if [[ -n "$public_bucket" ]]; then
      echo "Pulling the published map (BlueMap then renders only what changed)..."
      timed map-pull map_pull "$public_bucket" &
      map_job=$!
    fi
    restore_status=0
    wait "$restore_job" || restore_status=$?
    if [[ -n "$map_job" ]] && ! wait "$map_job"; then
      echo "warning: could not pull the published map; BlueMap renders it from scratch" >&2
    fi
    if (( restore_status != 0 )); then
      echo "ERROR: The restore of $snapshot failed (exit $restore_status)." >&2
      exit 1
    fi
    timed chown fix_owner
  fi
fi

# Never start without a world: Minecraft would generate a new one and the backup
# container would upload it over the real one's "latest".
if [[ ! -f data/minecraft/world/level.dat && "${NEW_WORLD:-}" != 1 ]]; then
  echo "ERROR: No world in data/minecraft. Use RESTORE=latest|<snapshot-id>, or NEW_WORLD=1 for a fresh world." >&2
  exit 1
fi

phase compose-up
echo "Updating containers and waiting for health checks..."
if ! "${compose[@]}" up -d --remove-orphans --wait --wait-timeout 600; then
  "${compose[@]}" ps >&2 || true
  echo "ERROR: Deployment did not become healthy. Inspect docker compose logs." >&2
  exit 1
fi

phase
"${compose[@]}" exec -T "$SERVICE" rcon-cli "say Deployment complete." || true
echo "Deployment completed; Minecraft health check passed."
