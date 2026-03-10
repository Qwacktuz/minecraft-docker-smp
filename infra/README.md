# Infrastructure Layer (OpenTofu)

This directory contains the OpenTofu (Terraform) configuration to provision the virtual hardware and bootstrap the OS for the Minecraft stack.

## Architecture

1. **Hetzner Cloud**: Provisions a VPS (default `cx33`) in `hel1`.
2. **Networking**:
    - Public IPv4/v6 enabled.
    - **Hetzner Firewall**: Blocks all public traffic except Minecraft (25565), Voice Chat (24454), and ephemeral ports. **SSH (22) is blocked from the public internet.**
3. **Tailscale**:
    - Automated join via `tailscale/tailscale` provider using OAuth.
    - Server joins with `tag:server`.
    - SSH is managed over the Tailscale tunnel.
4. **Bootstrap (Cloud-init)**:
    - Creates a `deployer` user.
    - Installs Docker (Standard).
    - Configures UFW (Host Firewall) as defense-in-depth.
    - Prepares the `~/app` directory and `.env.secrets`.

## Prerequisites

- **Hetzner Token**: `HCLOUD_TOKEN`.
- **Tailscale OAuth**:
  - Client ID and Secret with `Devices: Write` and `tag:server` permissions.
  - Tailnet name (e.g., `user.github`).
- **Tailscale ACLs**:
  - `tag:server` must be owned by the OAuth client or an admin.
  - SSH rules must allow `tag:ci` or your user to access `tag:server`.

## Usage

```bash
# Initialize providers
tofu init

# Deploy/Update infrastructure
tofu apply
```

## Secrets Management

OpenTofu securely uploads secrets to `/home/deployer/app/.env.secrets` on the target machine. These are then merged into a functional `.env` file by the GitHub Actions deployment workflow.
