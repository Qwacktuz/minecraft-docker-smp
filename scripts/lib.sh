# shellcheck shell=bash disable=SC2034 # the variables are used by the scripts that source this
# Shared by the scripts that run on the app host, and by bin/server on the
# laptop. They source it after `cd`ing into the app directory (the repository).

# Pinned images. Bump tag and digest together; the digest is the multi-arch
# index from `docker buildx imagetools inspect <image:tag>`. compose.yml pins the
# same backup image (tests/test_compose.py checks it).
BACKUP_IMAGE=itzg/mc-backup:2026.11.1@sha256:d731fa58822525cc65a23fbd82f472be4fc74854ee313da36bb4872bdba722c7
ALPINE_IMAGE=alpine:3.24.4@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf
JAVA_IMAGE=eclipse-temurin:25.0.5_8-jre@sha256:945247f9d092703e0c6be92243ef3c51640229e23ab34d353c8dcdc73e6cd4e6
RCLONE_IMAGE=rclone/rclone:1.76.0@sha256:7cbeec24a44f206067597c0368be4de90ae19a64d5113c7d1938bd737a81e466

# The restic host of the VPS backups (compose.yml RESTIC_HOST). Restores only
# consider these snapshots.
WORLD_HOST=mc-backup-worker

# The vault bucket: a copy of the backups that R2 bucket locks keep for 30
# days. The same restic repository (same password), written only by bin/server.
VAULT_BUCKET=${VAULT_BUCKET:-cactuz-mc-vault}

# restic <args>: runs restic against the R2 backups, with data/minecraft mounted
# at /data. The credentials come from ./.env (the app host), or from the
# environment when bin/server has already decrypted them (`secrets app`).
# RESTIC_SOURCE=vault reads the vault bucket instead, with the VAULT_* keys
# (`secrets all`). Values are passed by name (-e NAME), so secrets never
# appear in process lists.
restic() {
  (if [[ -f ./.env ]]; then
     set -a
     # shellcheck disable=SC1091
     . ./.env
     set +a
   fi
   [[ -n "${R2_ENDPOINT:-}" ]] || { echo "restic: no ./.env and no decrypted secrets" >&2; exit 1; }
   local bucket=$R2_BUCKET_NAME key_id=$R2_ACCESS_KEY_ID key=$R2_SECRET_ACCESS_KEY
   if [[ "${RESTIC_SOURCE:-}" == vault ]]; then
     bucket=$VAULT_BUCKET key_id=$VAULT_ACCESS_KEY_ID key=$VAULT_SECRET_ACCESS_KEY
   fi
   RESTIC_REPOSITORY="s3:${R2_ENDPOINT}/${bucket}"
   AWS_ACCESS_KEY_ID="$key_id" AWS_SECRET_ACCESS_KEY="$key"
   export RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
   docker run --rm --entrypoint restic -v "$PWD/data/minecraft:/data" \
     -e RESTIC_REPOSITORY -e RESTIC_PASSWORD -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
     "$BACKUP_IMAGE" -o s3.region=auto "$@")
}

# world_snapshot <id|latest>: prints the full ID of that snapshot, but only if
# it is one of WORLD_HOST's (restic ignores --host for an explicit ID). Fails
# when there is no such snapshot, or the ID prefix is ambiguous.
world_snapshot() {
  restic --no-lock snapshots --host "$WORLD_HOST" --json |
    python3 "$(dirname -- "${BASH_SOURCE[0]}")/snapshots.py" --find "$1"
}

# r2_rclone <user> <mount> <rclone args...>: runs rclone with the remote "r2:"
# set to R2, using the backup bucket's keys from ./.env (they can also write the
# public world bucket and WEB_BUCKET). <user> is a docker --user value or "root"; <mount> is a
# docker -v value (e.g. "$PWD/x:/work:ro"). Keys are passed by name (-e NAME),
# so they never appear in process lists.
r2_rclone() {
  local user=$1 mount=$2
  shift 2
  (set -a
   # shellcheck disable=SC1091
   . ./.env
   set +a
   export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare
   export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
   export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
   export RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT" RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
   local as=()
   [[ "$user" == root ]] || as=(--user "$user")
   docker run --rm "${as[@]}" -v "$mount" \
     -e RCLONE_CONFIG_R2_TYPE -e RCLONE_CONFIG_R2_PROVIDER -e RCLONE_CONFIG_R2_ACCESS_KEY_ID \
     -e RCLONE_CONFIG_R2_SECRET_ACCESS_KEY -e RCLONE_CONFIG_R2_ENDPOINT -e RCLONE_CONFIG_R2_NO_CHECK_BUCKET \
     "$RCLONE_IMAGE" "$@")
}

# Where BlueMap writes its web app and tiles (config/bluemap/webapp.conf), and
# where scripts/publish-map.sh publishes them in PUBLIC_WORLD_BUCKET.
MAP_WEB=data/minecraft/bluemap/web
MAP_PREFIX=map
# The same files as one tar, next to map/: one download instead of ~20,000.
MAP_ARCHIVE=map-state.tar

# Gives the world files back to the game's user (uid 1000). Only files someone
# else owns are changed (the map pull's, mostly): a restic restore as root
# already keeps the snapshot's owner, and the world has many small files.
fix_owner() {
  docker run --rm -v "$PWD/data/minecraft:/data" "$ALPINE_IMAGE" sh -c \
    'find /data \( ! -user 1000 -o ! -group 1000 \) -print0 | xargs -0 -r chown -h 1000:1000'
}

# --- Phase timings (docs/performance.md) ---------------------------------------
# `phase <name>` ends the running phase (if any) and starts <name>; `phase` with
# no name only ends it. Each finished phase prints "--- <name> <seconds>s",
# appends "<name> <seconds>" to $PHASE_LOG when that is set, and adds a table
# row to GitHub's step summary in Actions. bin/server collects the lines that
# deploy.sh prints on the VPS the same way (phase_lines).
PHASE_NAME=
PHASE_START=0
phase_done() {
  echo "--- $1 ${2}s"
  if [[ -n "${PHASE_LOG:-}" ]]; then echo "$1 $2" >> "$PHASE_LOG"; fi
  if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then echo "| $1 | ${2}s |" >> "$GITHUB_STEP_SUMMARY"; fi
  return 0
}
phase() {
  local now
  now=$(date +%s)
  if [[ -n "$PHASE_NAME" ]]; then phase_done "$PHASE_NAME" "$((now - PHASE_START))"; fi
  PHASE_NAME=${1:-}
  PHASE_START=$now
}
# `timed <name> <command...>` runs one command as its own phase and keeps its
# exit status; for jobs that run side by side (deploy.sh's restore).
timed() {
  local name=$1 start status=0
  shift
  start=$(date +%s)
  "$@" || status=$?
  phase_done "$name" "$(($(date +%s) - start))"
  return "$status"
}
