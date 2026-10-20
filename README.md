# Minecraft SMP

A Fabric Minecraft server deployed with Docker Compose, with Restic backups to
Cloudflare R2 and optional access to management tools over Tailscale. Infrastructure
provisioning currently targets Hetzner Cloud through OpenTofu.

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

Requirements: a Linux Docker host, Docker Compose v2.20+ (with `up --wait`),
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

## Deployment

The production workflow runs on pushes to `main` or manual dispatch. It serializes
runs, requires validation to pass, applies infrastructure and waits for server
Tailscale registration, joins Tailscale as `tag:ci`, waits for cloud-init,
locks deployment on the host, and checks out the triggering Git commit.

`scripts/deploy.sh` decrypts secrets into a private temporary file, validates the
Tailscale address and Compose settings, and pulls images before replacing `.env`.
It notifies players, requests a save, and waits for Minecraft health after updating.
Preflight failures preserve the existing `.env`. Images are not globally pruned.

**Existing installations:** complete the [one-time Loki migration](docs/loki-migration.md)
before the first deployment of the explicit Loki storage configuration. The deploy
script rejects the old layout to protect historical logs.

This remains a single-server deployment with downtime. Image/mod versions are
still mutable, infrastructure still auto-applies, and recovery scripts still need
further hardening. See the [baseline review](docs/production-readiness-review.md).

## Operations

Run from the application directory on the server:

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

## Validation and repository layout

```bash
python3 -m unittest discover -s tests -v
shellcheck scripts/deploy.sh
actionlint
tofu -chdir=infra fmt -check
tofu -chdir=infra init -backend=false -lockfile=readonly
tofu -chdir=infra validate
```

The validation workflow also checks Alloy/Loki configuration using their container
images. Tests use dummy credentials and mocked deployment commands; they never
contact production. A real restore-and-boot drill is still necessary before rollout.

- `compose.yml`, `scripts/`: active runtime and operations.
- `infra/`: Hetzner/Tailscale/DNS and cloud-init.
- `alloy/`, `grafana/`, `loki/`, `prometheus/`: active monitoring configuration.
- `secrets/`: encrypted runtime settings.
- `archive/`: inactive experiments, old inventory, and configuration notes;
  see its [index](archive/README.md). No archived files are loaded at runtime.
