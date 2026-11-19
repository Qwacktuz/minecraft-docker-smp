# Minecraft SMP

A Fabric Minecraft server in Docker Compose. The world is backed up with Restic
to Cloudflare R2. It runs either on your laptop or on a Hetzner VPS created on
demand with OpenTofu, which is deleted again when you stop it.

## Start and stop

One command, run from your laptop, decides where the world runs:

```bash
server start vps         # create the Hetzner VPS and run there: mc.cactuz.dev
server start local       # a read-only copy on this machine: localhost:25565
server stop              # VPS: final backup to R2, shut down, delete the VPS
server status            # where is it running, and when was the last backup?
server prune --dry-run   # which unused chunks would pruning delete?
server prune             # back up, then delete unused chunks on the VPS
server tofu plan         # run OpenTofu by hand with the encrypted credentials
```

(`server` is `bin/server`, on PATH inside the devenv shell.)

**There is one world, it lives in R2, and only the VPS writes to it.** On the VPS,
`stop` takes a backup and only shuts down once a snapshot newer than the stop
request appears in R2. Otherwise it aborts and leaves the server running. `start`
restores the newest VPS snapshot; the previous local data is kept in
`data/minecraft.previous`. The world runs in one place at a time: `start` refuses
while it runs elsewhere. Running `start` again where it already runs just
redeploys, without a restore. A brand-new world needs `NEW_WORLD=1` when R2 has
no snapshots.

**A local copy is read-only.** `start local` restores the newest VPS snapshot but
runs no backup service, reads R2 without writing lock files, and `stop` just shuts
it down. Whatever you do locally is never uploaded and is replaced by the next
restore. Restores only consider snapshots from the VPS backup host
(`mc-backup-worker`), so nothing else in the repository can become "latest".

**Pruning** deletes chunks nobody spent time in, while keeping builds, player
homes, recent activity and a buffer around them. It can also run automatically
every month on `stop`. Rules, dry runs and rollbacks: [docs/pruning.md](docs/pruning.md).

**A public world download.** Every VPS `stop` also uploads the world as
**https://world.cactuz.dev/world.zip**, after the final backup and with the game
stopped. It has no player data (inventories, positions, stats), so anyone can take a
copy to test redstone in singleplayer or on their own server; the zip's README.txt
explains how. It lives in its own public bucket (`PUBLIC_WORLD_BUCKET` in
`app.enc.env`), separate from the private backups. If the upload fails, `stop`
only warns. It updates at each stop, not while the server runs.

Deleting the VPS removes the server, firewall, DNS records and Tailscale device.
The R2 backups and the OpenTofu state are separate and are never deleted.
`start vps` deploys the current commit from GitHub, so push it first.

**Outside devenv you need:** a running Docker daemon (OrbStack or Docker Desktop),
the Tailscale app, and your Age key in `SOPS_AGE_KEY_FILE` (default
`~/.config/sops/age/keys.txt`).

## What runs

`compose.yml` has two services:

- **`minecraft-service`**: Fabric 26.3 with online authentication, an enforced
  whitelist, and the mod list in `MODRINTH_PROJECTS`. Public ports: game 25565/tcp,
  Simple Voice Chat 24454/udp, webcam 25454/udp. RCON is not published.
  On ARM64 hosts (e.g. Apple Silicon) `deploy.sh` uses Aikar's JVM flags instead
  of MeowIce's, which crash the JVM there.
- **`backup`**: `itzg/mc-backup` with Restic, VPS only (Compose profile `backup`).
  It backs up hourly, pausing when no players are online, and applies snapshot
  retention. Snapshots tagged `pre-prune` are kept for rollbacks.

The world is in `data/minecraft` (gitignored). On the VPS, the app lives in `~/app`.
Recovery from a specific snapshot is in [docs/how2backuprestore.md](docs/how2backuprestore.md).

Useful commands from the app directory:

```bash
docker compose logs -f minecraft-service
docker compose exec minecraft-service rcon-cli
docker compose exec backup backup now
docker compose exec backup restic snapshots
```

## Backups and their safety net

On the VPS, `stop` does these in order, and stops at any failure with the VPS still running:
1. Takes a backup.
2. Checks it reached R2.
3. Runs `restic check` on 2% of the data. The VPS disk is the only other copy of
   the world, so it isn't deleted while the backups look damaged.
4. Shuts down and publishes `world.zip`.
5. Deletes the VPS.
6. Copies the backup repository into the **vault** bucket from your laptop. That
   needs `rclone`, which devenv provides.

The vault only ever gains files. R2 bucket locks keep them for 30 days, and the VPS
has no key for it, so even a compromised server can't destroy the backups. Copy
again any time with `server vault`. Restoring from the vault:
[docs/how2backuprestore.md](docs/how2backuprestore.md#restore-from-the-vault).

## Secrets

Everything is SOPS/Age-encrypted in `secrets/`: `infra.enc.env` (laptop only:
OpenTofu, the state bucket, the vault) and `app.enc.env` (Compose, the VPS
backups). Edit them with `sops secrets/<file>`. Nothing secret is stored anywhere
else, and CI needs none. Each Cloudflare token reaches only its own buckets:
[infra/README.md](infra/README.md#cloudflare-tokens-and-buckets).

Every image is pinned to a version plus digest (`compose.yml`, `scripts/lib.sh`),
and so are CI's actions and devenv. Updates happen only when you bump them.

## Development environment

`devenv.nix` is the single source of tool versions, pinned in `devenv.lock`:
OpenTofu, Python, the Docker CLI with Compose, SOPS, Age, ShellCheck, actionlint,
curl and jq. Install [devenv](https://devenv.sh/getting-started/), then either run
`direnv allow` once (the shell loads on `cd`) or use `devenv shell`.

```bash
validate             # every check: tests, lint, tofu validate
devenv test          # git hooks + validate in a fresh shell; this is what CI runs
devenv update        # bump the pinned tool versions (commit devenv.lock)
```

Commits run ShellCheck, actionlint, nixfmt and `tofu fmt` hooks. CI runs
`devenv test` on every push and pull request and never touches a server. The
tests use mocks and dummy credentials.

## Layout

- `bin/server`, `scripts/deploy.sh`: start/stop and deployment.
- `scripts/prune.sh`, `scripts/prune_plan.py`, `prune/`: chunk pruning and its rules.
- `scripts/publish-world.sh`, `scripts/world_zip.py`: the public `world.zip`.
- `scripts/restore-backup.sh`, `restore-regions.sh`, `rollback-backup.sh`,
  `test-backup.sh`: manual backup tools, run on the app host. They share
  `scripts/lib.sh` (pinned images, and restic with secrets passed by name).
- `compose.yml`, `static/icon.png`: the game and its backups.
- `infra/`: Hetzner VPS, firewall, DNS, Tailscale bootstrap, cloud-init.
- `secrets/`: SOPS-encrypted settings.
- `tests/`: mocked lifecycle and configuration tests.

Removed configurations (monitoring stack, Arcane, the `bin/smp` experiment, the
old archive) are in Git history; see [CHANGELOG.md](CHANGELOG.md).
