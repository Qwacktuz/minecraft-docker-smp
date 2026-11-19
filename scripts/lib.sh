# shellcheck shell=bash disable=SC2034 # the variables are used by the scripts that source this
# Shared by the scripts that run on the app host, and by bin/server on the
# laptop. They source it after `cd`ing into the app directory (the repository).

# Pinned images. Bump tag and digest together; the digest is the multi-arch
# index from `docker buildx imagetools inspect <image:tag>`. compose.yml pins the
# same backup image (tests/test_compose.py checks it).
BACKUP_IMAGE=itzg/mc-backup:2026.11.1@sha256:d731fa58822525cc65a23fbd82f472be4fc74854ee313da36bb4872bdba722c7
ALPINE_IMAGE=alpine:3.24.4@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf
JAVA_IMAGE=eclipse-temurin:25.0.5_8-jre@sha256:945247f9d092703e0c6be92243ef3c51640229e23ab34d353c8dcdc73e6cd4e6
RCLONE_IMAGE=rclone/rclone:1.75.2@sha256:2687085f718d3c628f7fdfb77c52a1d344332aed543110bb88088f2c70d43eb5

# The restic host of the VPS backups (compose.yml RESTIC_HOST). Restores only
# consider these snapshots.
WORLD_HOST=mc-backup-worker

# restic <args>: runs restic against the R2 backups with the credentials in
# ./.env, and data/minecraft mounted at /data. Values are passed by name
# (-e NAME), so secrets never appear in process lists.
restic() {
  (set -a
   # shellcheck disable=SC1091
   . ./.env
   set +a
   RESTIC_REPOSITORY="s3:${R2_ENDPOINT}/${R2_BUCKET_NAME}"
   AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
   export RESTIC_REPOSITORY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
   docker run --rm --entrypoint restic -v "$PWD/data/minecraft:/data" \
     -e RESTIC_REPOSITORY -e RESTIC_PASSWORD -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
     "$BACKUP_IMAGE" -o s3.region=auto "$@")
}

# Gives the world files back to the game's user (uid 1000).
fix_owner() { docker run --rm -v "$PWD/data/minecraft:/data" "$ALPINE_IMAGE" chown -R 1000:1000 /data; }
