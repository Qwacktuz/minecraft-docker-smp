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

# Gives the world files back to the game's user (uid 1000).
fix_owner() { docker run --rm -v "$PWD/data/minecraft:/data" "$ALPINE_IMAGE" chown -R 1000:1000 /data; }
