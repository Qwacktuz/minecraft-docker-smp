#!/usr/bin/env bash
# Deletes rarely visited chunks from the world with MCA Selector (headless).
# Runs on the host that holds the world, from the app directory:
#
#   bash scripts/prune.sh --dry-run   report only; selections go to .cache/prune/
#   bash scripts/prune.sh             delete (the game must be stopped)
#
# The keep rules live in prune/settings.env and prune/protect.txt. `bin/server
# prune` wraps this with a backup before and a restart after.
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"

MCASELECTOR_VERSION=2.9 # supports Minecraft 26.3
MCASELECTOR_SHA256=8e35eaa6a5119ce711b53530c22aaac531332e8fdffda2357d16eb6f52327267
JAVA_IMAGE=eclipse-temurin:25-jre
WORLD=data/minecraft/world
OUT=.cache/prune
JAR=.cache/mcaselector-$MCASELECTOR_VERSION.jar

die() { echo "prune: $*" >&2; exit 1; }

dry_run=0
case "${1:-}" in
  --dry-run) dry_run=1 ;;
  "") ;;
  *) die "usage: prune.sh [--dry-run]" ;;
esac

set -a
# shellcheck disable=SC1091 # prune/settings.env
. prune/settings.env
set +a
export PRUNE_PROTECT="$APP_DIR/prune/protect.txt"

[[ -f "$WORLD/level.dat" ]] || die "no world in $WORLD"
if (( ! dry_run )) &&
   docker compose ps --status running --services 2>/dev/null | grep -qx minecraft-service; then
  die "the game is running; stop it first (bin/server prune does this)"
fi

sha256() { python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"; }
mkdir -p "$OUT"
if [[ ! -f "$JAR" || "$(sha256 "$JAR")" != "$MCASELECTOR_SHA256" ]]; then
  echo "Downloading MCA Selector $MCASELECTOR_VERSION..."
  curl -fsSL -o "$JAR.tmp" \
    "https://github.com/Querz/mcaselector/releases/download/$MCASELECTOR_VERSION/mcaselector-$MCASELECTOR_VERSION.jar"
  [[ "$(sha256 "$JAR.tmp")" == "$MCASELECTOR_SHA256" ]] || { rm -f "$JAR.tmp"; die "MCA Selector checksum mismatch"; }
  mv "$JAR.tmp" "$JAR"
fi

# Runs as the game's user (1000) so rewritten region files keep their owner.
mcaselector() {
  docker run --rm --user 1000:1000 -v "$APP_DIR/$WORLD:/world" -v "$APP_DIR/.cache:/cache" \
    "$JAVA_IMAGE" java -Xmx3G -jar "/cache/mcaselector-$MCASELECTOR_VERSION.jar" "$@"
}
# Captures MCA Selector's progress output and shows it only on failure.
quietly() {
  local log=$1; shift
  "$@" > "$log" 2>&1 || { tr '\r' '\n' < "$log" | tail -n 20 >&2; die "MCA Selector failed (log: $log)"; }
}

# Plan every dimension first, so a refusal deletes nothing anywhere.
dimensions=()
for dim in overworld the_nether the_end; do
  dir=dimensions/minecraft/$dim
  [[ -d "$WORLD/$dir/region" ]] || continue
  rm -f "$OUT/$dim"-*.csv
  # Chunks to keep, widened by the buffer ring.
  quietly "$OUT/$dim-keep.log" mcaselector --mode select --world "/world/$dir" \
    --region "/world/$dir/region" --query "$(python3 scripts/prune_plan.py keep "$WORLD" "$dim")" \
    --radius "$PRUNE_BUFFER" --output "/cache/prune/$dim-keep.csv"
  [[ -s "$OUT/$dim-keep.csv" ]] || die "$dim: the keep query selected nothing; refusing to prune"
  # Chunks MCA Selector read and found failing every rule. Unreadable chunks
  # are in neither selection, so they are never deleted.
  quietly "$OUT/$dim-candidates.log" mcaselector --mode select --world "/world/$dir" \
    --region "/world/$dir/region" --query "$(python3 scripts/prune_plan.py candidates "$WORLD" "$dim")" \
    --output "/cache/prune/$dim-candidates.csv"
  python3 scripts/prune_plan.py plan "$WORLD" "$dim" "$OUT/$dim-keep.csv" \
    "$OUT/$dim-candidates.csv" "$OUT/$dim-delete.csv" || die "nothing was deleted"
  dimensions+=("$dim")
done

if (( dry_run )); then
  echo "Dry run: nothing was deleted. To view a selection, open a copy of the world in"
  echo "MCA Selector and use Selection > Import selection with $OUT/<dimension>-delete.csv."
  exit 0
fi

for dim in "${dimensions[@]}"; do
  dir=dimensions/minecraft/$dim
  [[ -s "$OUT/$dim-delete.csv" ]] || continue
  echo "Deleting chunks in $dim..."
  folders=(--region "/world/$dir/region")
  for kind in poi entities; do
    [[ -d "$WORLD/$dir/$kind" ]] && folders+=("--$kind" "/world/$dir/$kind")
  done
  quietly "$OUT/$dim-delete.log" mcaselector --mode delete --world "/world/$dir" \
    "${folders[@]}" --selection "/cache/prune/$dim-delete.csv"
done
echo "Prune complete."
