# 🎮 infra-minecraft

A high-performance, automated, and secure Minecraft server stack (Fabric) deployed on Hetzner Cloud.

## 🛠 Features

- **Infrastructure**: Managed with **OpenTofu** (Hetzner + Tailscale OAuth).
- **Security**: **Tailscale-only SSH** (HCloud restricted to runner IP). **UFW** host firewall. **SOPS** + **Age** for secret management.
- **Observability**: **Grafana**, **Prometheus**, **Loki**, **Alloy** (Telemetry Pipeline), and **Portainer** (via `compose.yml`).
- **Backups**: Automated **Restic** backups to Cloudflare R2 (S3-compatible) every hour.
- **CI/CD**: Fully automated **GitHub Actions** deployment over the Tailscale network with RCON-based status notifications.

## 🚀 Deployment Workflow

1. **OpenTofu**: Provisions the server and bootstraps Docker/Tailscale (`infra/` directory).
2. **GitHub Actions**:
   - Connects to the Tailscale network as `tag:ci`.
   - Merges secrets using **SOPS** and **Age**.
   - Pulls latest images and restarts the Docker Compose stack over the private network.
   - Sends RCON notifications to the server during the deployment process.
3. **Secrets**: Decrypted at runtime on the host via SOPS and injected into the `.env` file.

## 💾 Commands

**Quick commands for management (Run on Server)**

```bash
# Drop into container
docker exec -it fabric-server bash

# Execute in game commands (RCON)
docker exec -it fabric-server rcon-cli

# List all running containers
docker ps

# List container logs
docker compose logs -f minecraft-service

# Minecraft healthcheck
docker container inspect -f "{{.State.Health.Status}}" fabric-server

# Spin up stack/stop stack
docker compose up -d
docker compose down
```

**Backup management (Restic)**

```bash
# Force a backup NOW
docker compose exec backup backup now

# View snapshots
docker compose exec backup restic snapshots

# Restore the LATEST backup (Interactive)
./scripts/restore-backup.sh

# List backed up files
docker compose exec backup restic ls latest

# Actually delete data (Maintenance)
docker compose exec backup restic forget --keep-last 7 --prune
```

## 🔧 Infrastructure Management

See the [infra/README.md](./infra/README.md) for details on provisioning the VPS and managing Tailscale OAuth.

## TODO

- Replace parts of cloudinit with ansible
