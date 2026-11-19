# Minecraft SMP

A Fabric Minecraft server deployed with Docker Compose, with Restic backups to
Cloudflare R2 and optional access to management tools over Tailscale. Infrastructure
provisioning currently targets Hetzner Cloud through OpenTofu.

The replacement architecture is being implemented incrementally. Start with the
[local-core code review and workflow exercise](docs/local-core-checkpoint.md).
Its controller uses a separate Compose file; the commands below describe the
existing production stack.

## Components

- **Game:** Fabric, online authentication, enforced whitelist, voice/webcam mods.
- **Backups:** Restic, hourly interval with scheduling paused when no players are online.
- **Monitoring:** Grafana, Prometheus, Loki, and Alloy. Minecraft logs are read from
  files without granting Alloy Docker socket access. Minecraft metrics remain
  unavailable until a compatible Fabric exporter is enabled.
- **Management:** Arcane, which has privileged Docker socket access.
- **Secrets:** SOPS/Age-encrypted configuration; deployment creates a private `.env`.
- **Access:** Public game/voice/webcam ports; management ports bound to an explicit
  host address. Public SSH is blocked by the configured Hetzner firewall.

## Configuration

Requirements: a Docker host with Compose v2.20+ (with `up --wait`),
Tailscale, SOPS, Bash, and the credentials described in [infra/README.md](infra/README.md).
The default host configuration targets AMD64 and an 8 GB server; it is not a
complete portable homelab/local-copy installer yet.

For manual setup, copy `.env.example` to `.env`, set permissions to `600`, and fill
in every required value. `MC_OPS` may be empty; `MC_WHITELIST` must not be empty.
Follow the image's username-list format for both. Use independent random secrets;
Arcane encryption/JWT keys must meet Arcane's requirements. Preserve the Restic
password separately: losing it makes backups unreadable.

`TS_IP=127.0.0.1` restricts **management** endpoints to the local host. Production
uses the host's Tailscale IPv4. Game TCP 25565 and voice/webcam UDP 24454/25454 remain
publicly bound in either case. Do not reuse production backup write credentials
for a local copy.

```bash
docker compose config --quiet
docker compose up -d --wait --wait-timeout 600
docker compose ps
```

This starts a new world when `data/minecraft` is empty. For recovery, follow
[backup and restore](docs/how2backuprestore.md) before starting the stack.

## Start and stop

One command, run from your laptop, decides where the world runs:

```bash
bin/server start local   # Docker on this machine: localhost:25565
bin/server start vps     # create the Hetzner VPS and run there: mc.cactuz.dev
bin/server stop          # final backup to R2, shut down, delete the VPS
bin/server status        # where is it running, and when was the last backup?
```

**There is one world, and it lives in R2.** `stop` takes a backup and only shuts
down once a snapshot newer than the stop request appears in R2. Otherwise it
aborts and leaves the server running. `start` always restores the newest
snapshot (the previous local data is kept in `data/minecraft.previous`). The
world runs in one place at a time: `start` refuses while it runs elsewhere.
Running `start` again where it already runs just redeploys, without a restore.
A brand-new world needs `NEW_WORLD=1` when R2 has no snapshots.

Deleting the VPS removes the server, firewall, DNS records and Tailscale device.
The R2 backups and the OpenTofu state are separate and are never deleted.

**Laptop requirements:** [devenv](https://devenv.sh) provides every tool
(see [Development environment](#development-environment)). Outside it you need
a running Docker daemon (OrbStack or Docker Desktop), the Tailscale app, and your
Age key in `SOPS_AGE_KEY_FILE` (default `~/.config/sops/age/keys.txt`). Every secret
is SOPS-encrypted in `secrets/` (see [infra/README.md](infra/README.md#secrets)).
`start vps` deploys the current commit from GitHub, so push it first.

Under the hood: `bin/server` runs `tofu apply`/`destroy` and calls
`scripts/deploy.sh` (locally, or on the VPS over Tailscale SSH). The deploy
script decrypts secrets, restores the world when asked, and waits for health.
CI only validates; pushing to `main` never creates or changes a server.

**Existing installations:** complete the [one-time Loki migration](docs/loki-migration.md)
before the first deployment of the explicit Loki storage configuration. The deploy
script rejects the old layout to protect historical logs.

## Operations

Run from the application directory (`~/app` on the VPS, the repository locally):

```bash
docker compose logs -f minecraft-service
docker compose exec minecraft-service rcon-cli
docker compose exec backup backup now
docker compose exec backup restic snapshots
docker compose stop
```

Minecraft has a two-minute shutdown grace period. All services use Docker's `local`
log driver, bounded to three 10 MB files per container. This does not bound world,
Loki, or Prometheus data growth. Keep disk-space monitoring in place.

Management endpoints use the configured `TS_IP`: Grafana `3000`, Prometheus `9090`,
Loki `3100`, Alloy `12345`, and Arcane `3552`. RCON is not published on the host.
Tailnet policy must restrict access to the appropriate administrators.

## Development environment

`devenv.nix` is the single source of tool versions (pinned in `devenv.lock`):
OpenTofu, Python, the Docker CLI with Compose, SOPS, Age, SecretSpec, ShellCheck,
actionlint and jq. Install [devenv](https://devenv.sh/getting-started/), then either
run `direnv allow` once (the shell loads on `cd`) or use `devenv shell`.

```bash
server start local   # bin/server, available on PATH in the shell
validate             # every check: tests, lint, tofu, Alloy/Loki configs
devenv test          # git hooks + validate in a fresh shell; this is what CI runs
devenv update        # bump the pinned tool versions (commit devenv.lock)
```

Commits run ShellCheck, actionlint, nixfmt and `tofu fmt` hooks. The Alloy/Loki
checks need Docker running; locally they're skipped with a notice when it isn't.

## Validation and repository layout

CI runs `devenv test` on every push and pull request. Tests use dummy credentials and mocked deployment commands; they never
contact production. A real restore-and-boot drill is still necessary before rollout.

- `compose.yml`, `scripts/`: active runtime and operations.
- `infra/`: Hetzner/Tailscale/DNS and cloud-init.
- `alloy/`, `grafana/`, `loki/`, `prometheus/`: active monitoring configuration.
- `secrets/`: encrypted runtime settings.
- `archive/`: inactive experiments, old inventory, and configuration notes;
  see its [index](archive/README.md). No archived files are loaded at runtime.
