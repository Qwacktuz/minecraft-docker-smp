# Minecraft SMP

A Fabric Minecraft server in Docker Compose. The world is backed up with Restic
to Cloudflare R2. It runs either on your laptop or on a Hetzner VPS created on
demand with OpenTofu, which is deleted again when you stop it.

## Start and stop

One command, run from your laptop, decides where the world runs:

```bash
server start local   # Docker on this machine: localhost:25565
server start vps     # create the Hetzner VPS and run there: mc.cactuz.dev
server stop          # final backup to R2, shut down, delete the VPS
server status        # where is it running, and when was the last backup?
server tofu plan     # run OpenTofu by hand with the encrypted credentials
```

(`server` is `bin/server`, on PATH inside the devenv shell.)

**There is one world, and it lives in R2.** `stop` takes a backup and only shuts
down once a snapshot newer than the stop request appears in R2. Otherwise it
aborts and leaves the server running. `start` always restores the newest
snapshot; the previous local data is kept in `data/minecraft.previous`. The world
runs in one place at a time: `start` refuses while it runs elsewhere. Running
`start` again where it already runs just redeploys, without a restore. A
brand-new world needs `NEW_WORLD=1` when R2 has no snapshots.

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
- **`backup`**: `itzg/mc-backup` with Restic. It backs up hourly, pausing when
  no players are online, and prunes old snapshots.

The world is in `data/minecraft` (gitignored). On the VPS, the app lives in `~/app`.
Recovery from a specific snapshot is in [docs/how2backuprestore.md](docs/how2backuprestore.md).

Useful commands from the app directory:

```bash
docker compose logs -f minecraft-service
docker compose exec minecraft-service rcon-cli
docker compose exec backup backup now
docker compose exec backup restic snapshots
```

## Secrets

Everything is SOPS/Age-encrypted in `secrets/`: `infra.enc.env` for OpenTofu and
`app.enc.env` for Compose. Edit them with `sops secrets/<file>`. Nothing secret is
stored anywhere else, and CI needs none. Details: [infra/README.md](infra/README.md#secrets).

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
- `scripts/restore-backup.sh`, `rollback-backup.sh`, `test-backup.sh`: manual
  backup tools, run on the app host.
- `compose.yml`, `static/icon.png`: the game and its backups.
- `infra/`: Hetzner VPS, firewall, DNS, Tailscale bootstrap, cloud-init.
- `secrets/`: SOPS-encrypted settings.
- `tests/`: mocked lifecycle and configuration tests.

Removed configurations (monitoring stack, Arcane, the `bin/smp` experiment, the
old archive) are in Git history; see [CHANGELOG.md](CHANGELOG.md).
