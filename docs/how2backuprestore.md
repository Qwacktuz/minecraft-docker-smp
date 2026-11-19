# Backup and recovery

Run commands from the app directory (`~/app` on the VPS; set `APP_DIR` to use
`restore-backup.sh` elsewhere). The scripts read `.env` as shell syntax. They are not yet a fully automated disaster-recovery
system. Do not run restoration concurrently with deployment or other maintenance.

## Select a recovery point

```bash
docker compose exec backup backup now
docker compose exec backup restic snapshots
```

Wait for successful completion, then record an **explicit snapshot ID** and the
Git/image/mod versions it belongs to. Do not rely on `latest` during migration:
a fresh server can create and back up a new world before restoration.

`bash scripts/test-backup.sh` checks repository metadata and lists snapshots. It
does not prove a world can boot. Periodically run data-read integrity checks and
restore onto an isolated host.

## Restore on an existing host

Keep enough free disk for both current and restored state. Obtain the correct
runtime configuration and compatible release before restoring. Set `SNAPSHOT_ID`
to the recorded ID, then run the block below. It stops on errors and leaves backups
stopped if recovery fails; inspect the failure before resuming them.

```bash
SNAPSHOT_ID=replace-with-recorded-id
(
  set -euo pipefail
  exec 9>"$HOME/.minecraft-deploy.lock"
  flock -n 9
  docker compose stop backup
  bash scripts/restore-backup.sh "$SNAPSHOT_ID"
  docker compose up -d --wait --wait-timeout 600 minecraft-service
  docker compose up -d --force-recreate backup
)
```

Stopping and recreating the worker matters: it must not retain a bind mount to the
pre-restore directory. Verify the world and mod state in-game, then check that a new
backup contains the restored instance's current data. The script's completion message
alone is not evidence of recovery. Retain `data/minecraft_pre_restore_*` until verified.

The rollback script deletes the current world directory. Preserve any data you need
first, stop the backup worker, and use the same maintenance lock. Recreate the worker
after rollback and verify health before reopening the server.

## Moving the world between hosts

`bin/server stop` takes and verifies a final backup; `bin/server start local|vps`
restores the newest snapshot before the server starts. That is the normal way to
move the world; use the manual steps above only to recover an *older* snapshot.
