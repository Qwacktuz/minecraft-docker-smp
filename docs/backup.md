# Backup and recovery

The world is backed up hourly to R2 by the VPS (restic host `mc-backup-worker`),
and copied into the vault bucket (`cactuz-mc-vault`) after every stop. Every
command here only considers `mc-backup-worker` snapshots.

## From the laptop: list, check, drill (read-only)

These need the Age key and Docker (restic runs in the pinned backup image),
but no VPS. They write nothing to R2 or the vault.

```bash
server backups               # snapshots in R2: ID, time, tags (pre-prune, pre-restore)
server backups --vault       # the same for the vault, which keeps older snapshots too
server check                 # restic check, reading 5% of the data
server check 25              # read 25% of the data
server check 10 --vault      # check the vault instead
server drill                 # restore the newest vault snapshot locally, start it, stop it
server drill <id>            # the same for one snapshot
```

`server unpin <id>` removes the `pre-prune` pin from a snapshot once its pruned
world is checked in game ([pruning.md](pruning.md)). It is the one backup command
that writes, and only that tag.

- `check` runs `scripts/test-backup.sh` here without a lock (`--no-lock`), so
  it doesn't block a running VPS's backups. If the VPS prunes old snapshots at
  the same moment, the check can report missing data; run it again.
- `drill` is a full restore test from the vault alone: it restores into
  `data/minecraft` like `start local` (the previous local copy goes to
  `data/minecraft.previous`), waits until the game passes its health check, then
  runs `docker compose down`. It refuses while a local copy runs.

## Restore an older snapshot (admins)

```bash
server backups                                     # pick the ID
server restore <id>                                # the whole world
server restore <id> --region overworld 1200 -340   # one region file
server restore <id> --region nether -80 45 300     # every region within 300 blocks
server rollback                                    # undo the last restore
```

Add `--yes` to skip the question. These run from the laptop only; the GitHub
workflow only starts and stops.

**With the VPS running**, `restore` asks first, then:
1. takes a backup and checks it reached R2 (as `stop` does), and tags it
   `pre-restore`: the **safety backup**;
2. on the VPS, under the deploy lock, stops the backup container, runs
   `scripts/restore.sh world <id>` (the current world moves to
   `data/minecraft_pre_restore_<time>`; the game restarts when done), and
   recreates the backup container. It must not keep the old world mounted.

The next hourly backup then holds the restored world. Players lose everything
since `<id>`.

**`--region <dimension> <x> <z> [radius]`** restores only the region files
around a block position (F3 coordinates; dimension `overworld`, `nether` or
`end`). A region file holds 512×512 blocks, so block x is in region
`floor(x / 512)`: block -1 is in `r.-1.*`, block 511 in `r.0.*`. With a radius,
every region file touching the square from x-radius,z-radius to
x+radius,z+radius is restored, with its `entities/` and `poi/` files, via
`scripts/restore.sh regions`. It lists the files and asks first, and takes the
same safety backup. It needs the VPS.

**With nothing running**, `restore <id>` starts a **read-only local copy** of
`<id>` instead (like `start local`), to look at an old state without changing
anything.

**`rollback`** restores the newest `pre-restore` safety backup. It lives in R2, so:
- VPS running: it takes a new safety backup (so the rollback can be undone too)
  and restores the old one.
- VPS deleted since: it asks, then runs `start vps` from the safety backup
  instead of the newest snapshot.
- It refuses while a local copy runs.

The newest 3 safety backups keep the `pre-restore` tag, and retention keeps
tagged snapshots (`PRUNE_RESTIC_RETENTION` in compose.yml). Older ones fall back
to normal retention; the vault keeps them all.

## Select a recovery point by hand

```bash
docker compose exec backup backup now
docker compose exec backup restic snapshots
```

Wait for successful completion, then record an **explicit snapshot ID** and the
Git/image/mod versions it belongs to. Do not rely on `latest` during migration:
a fresh server can create and back up a new world before restoration.

`bash scripts/test-backup.sh` checks the repository, lists snapshots and reads a
sample of the data. It does not prove a world can boot; `server drill` does.

## Restore on an existing host by hand

`server restore` does this for you. By hand, from the app directory (`~/app`
on the VPS; set `APP_DIR` to use `scripts/restore.sh` elsewhere):

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
  bash scripts/restore.sh world "$SNAPSHOT_ID"
  docker compose up -d --wait --wait-timeout 600 minecraft-service
  docker compose up -d --force-recreate backup
)
```

Stopping and recreating the worker matters: it must not retain a bind mount to the
pre-restore directory. Verify the world and mod state in-game, then check that a new
backup contains the restored instance's current data. The script's completion message
alone is not evidence of recovery. Retain `data/minecraft_pre_restore_*` until verified.

`bash scripts/restore.sh rollback` puts the newest `data/minecraft_pre_restore_*`
back from the VPS disk, so it only works while that VPS exists; `server rollback`
restores the safety snapshot from R2 instead. It deletes the current world directory. Preserve any data you need
first, stop the backup worker, and use the same maintenance lock. Recreate the worker
after rollback and verify health before reopening the server.

## Moving the world between hosts

`bin/server stop` takes and verifies a final backup; `bin/server start local|vps`
restores the newest snapshot before the server starts. That is the normal way to
move the world; use the manual steps above only to recover an *older* snapshot.

## Restore from the vault

If the backup bucket is ever damaged or emptied, the vault (`cactuz-mc-vault`) holds
a full copy of the repository with the same password. On the laptop:

```bash
sops exec-env secrets/infra.enc.env 'sops exec-env secrets/app.enc.env "
  RESTIC_REPOSITORY=s3:\$R2_ENDPOINT/cactuz-mc-vault \
  AWS_ACCESS_KEY_ID=\$VAULT_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=\$VAULT_SECRET_ACCESS_KEY \
  restic --no-lock -o s3.region=auto snapshots"'
```

`server backups --vault`, `server check --vault` and `server drill` read the vault
without this. To restore from it, copy it back with `rclone`, or point a restore at it the same
way. The vault never deletes anything, so it also holds snapshots that retention
has already removed from the backup bucket.

## Checking the backups

`server stop` checks 2% of the data every time. For a deeper check, run
`server check 25` from the laptop (or `bash scripts/test-backup.sh 25` on the VPS).
`scripts/restore.sh` and `deploy.sh` refuse snapshot IDs that aren't
`mc-backup-worker` snapshots, and ambiguous ID prefixes.

Only the VPS runs the backup service, so the `docker compose exec backup ...`
commands above work there only. A local copy (`start local`) is read-only and never
creates snapshots. To undo a chunk prune, use the `pre-prune` snapshots; see
[pruning.md](pruning.md#undoing-a-prune).
