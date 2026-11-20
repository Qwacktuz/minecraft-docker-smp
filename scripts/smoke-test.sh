#!/usr/bin/env bash
# Boots compose.yml with a fresh, throwaway world and placeholder secrets, to
# check that the mod list and config/ load. A dev tool: it needs Docker and the
# internet (Modrinth, Mojang, Fabric), never touches R2 or data/minecraft, and
# CI does not run it.
#
#   scripts/smoke-test.sh [--keep] [check...]
#   scripts/smoke-test.sh down          remove a run left by --keep
#
# Each check runs once the game is healthy; any failing check fails the test:
#   rcon:<command>     an RCON command (prints the reply)
#   sh:<command>       a shell command inside the game container
#   host:<command>     a shell command here; $SMOKE_DATA is the server's /data
#   log:<regex>        the server log must match this extended regex
# --keep leaves the server running (container mc-smoke) for a look by hand.
# SMOKE_COMPOSE_EXTRA=<file> adds one more Compose file, e.g. proxy settings
# for a sandbox whose containers can't reach the internet directly.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
# shellcheck source=lib.sh
. scripts/lib.sh
WORK=$ROOT/.cache/smoke
export SMOKE_DATA=$WORK/data
PROJECT=mc-smoke
# The log lines that mean a mod failed to load or crashed the startup.
FATAL='Incompatible mods? found|Mixin apply.*failed|InvalidInjectionException|FormattedException|Could not find required mod|requires (any version|version) .* of|Failed to start the minecraft server|Encountered an unexpected exception|Exception in server tick loop'

die() { echo "smoke-test: $*" >&2; exit 1; }
compose() {
  docker compose -p "$PROJECT" --env-file "$WORK/env" -f compose.yml -f "$WORK/override.yml" \
    ${SMOKE_COMPOSE_EXTRA:+-f "$SMOKE_COMPOSE_EXTRA"} "$@"
}

clean() {
  if [[ -f "$WORK/override.yml" ]]; then compose down -v --remove-orphans >/dev/null 2>&1 || true; fi
  # The game writes as uid 1000; remove its files from a container.
  if [[ -d "$WORK" ]]; then
    docker run --rm -v "$ROOT/.cache:/c" "$ALPINE_IMAGE" rm -rf /c/smoke
  fi
}

keep=
checks=()
for arg; do
  case "$arg" in
    down) clean; echo "smoke-test: removed."; exit 0 ;;
    --keep) keep=1 ;;
    rcon:* | sh:* | host:* | log:*) checks+=("$arg") ;;
    *) die "unknown argument '$arg' (see the top of $0)" ;;
  esac
done

clean
mkdir -p "$SMOKE_DATA"
cat > "$WORK/env" <<EOF
MC_WHITELIST=Notch
MC_OPS=
RCON_PASSWORD=smoke-$RANDOM$RANDOM
R2_ENDPOINT=https://invalid.example
R2_BUCKET_NAME=none
R2_ACCESS_KEY_ID=none
R2_SECRET_ACCESS_KEY=none
RESTIC_PASSWORD=none
COMPOSE_PROFILES=
EOF
# Own container name, own data, no published ports: it can run beside a real
# local copy. Volumes merge by container path, so /data is replaced.
cat > "$WORK/override.yml" <<EOF
services:
  minecraft-service:
    container_name: $PROJECT
    ports: !reset []
    environment:
      SEED: "smoke-test"
    volumes:
      - $SMOKE_DATA:/data
EOF
case "$(docker info --format '{{.Architecture}}')" in
  aarch64 | arm64) printf 'USE_MEOWICE_FLAGS=false\nUSE_AIKAR_FLAGS=true\n' >> "$WORK/env" ;;
esac
[[ -z "${SMOKE_COMPOSE_EXTRA:-}" || -f "$SMOKE_COMPOSE_EXTRA" ]] || die "no file $SMOKE_COMPOSE_EXTRA"
[[ -n "$keep" ]] || trap 'clean' EXIT

echo "smoke-test: starting a fresh world (first start downloads every mod; up to 15 minutes)..."
status=0
compose up -d --wait --wait-timeout 900 minecraft-service || status=$?
compose logs --no-color --no-log-prefix minecraft-service > "$ROOT/.cache/smoke-server.log" 2>&1 || true
log=$ROOT/.cache/smoke-server.log
if (( status != 0 )); then
  tail -n 60 "$log" >&2
  die "the server did not become healthy (full log: .cache/smoke-server.log)"
fi

failed=0
if grep -En "$FATAL" "$log" >&2; then
  echo "smoke-test: FAIL: mod or startup errors above" >&2
  failed=1
fi
mods=$(grep -Eo 'Loading [0-9]+ mods' "$log" | head -n1 || true)
errors=$(grep -c '/ERROR\]' "$log" || true)
echo "smoke-test: healthy. ${mods:-mod count not logged}; $errors ERROR lines (listed below)."
grep '/ERROR\]' "$log" | cut -c1-240 | sort | uniq -c | sort -rn | head -n 20 || true

for check in "${checks[@]}"; do
  kind=${check%%:*} body=${check#*:}
  echo "--- $check"
  case "$kind" in
    rcon) out=$(compose exec -T minecraft-service rcon-cli "$body" 2>&1) || failed=1; echo "$out" ;;
    sh) compose exec -T minecraft-service sh -c "$body" || { echo "FAILED" >&2; failed=1; } ;;
    host) bash -c "$body" || { echo "FAILED" >&2; failed=1; } ;;
    log)
      compose logs --no-color --no-log-prefix minecraft-service > "$log" 2>&1 || true
      grep -Em3 "$body" "$log" || { echo "FAILED: no log line matches" >&2; failed=1; } ;;
  esac
done

if [[ -n "$keep" ]]; then
  echo "smoke-test: still running as container $PROJECT; remove it with: scripts/smoke-test.sh down"
fi
(( failed == 0 )) || die "FAILED (log: .cache/smoke-server.log)"
echo "smoke-test: PASSED"
