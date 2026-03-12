# Infrastructure Layer (OpenTofu)

This directory contains the OpenTofu (Terraform) configuration to provision the virtual hardware and bootstrap the OS for the Minecraft stack.

## Architecture

1. **Hetzner Cloud**: Provisions a VPS (default `cx33`) in `hel1` running **Debian 13 (Trixie)**.
2. **Networking**:
    - Public IPv4/v6 enabled.
    - **Hetzner Firewall**: Blocks all public traffic except Minecraft (25565), Voice Chat (24454), and ephemeral ports. **SSH (22) is restricted to the CI runner's IP.**
3. **Tailscale**:
    - Automated join via `tailscale/tailscale` provider using ephemeral Auth Keys.
    - Server joins with `tag:server` and hostname `mc-prod`.
    - SSH is managed over the Tailscale tunnel (via `tailscale0` in UFW).
4. **Bootstrap (Cloud-init)**:
    - Creates a `deployer` user.
    - Installs Docker, SOPS, Age, UFW, Fail2ban.
    - Configures SSH hardening and Host Firewall.

## Prerequisites

- **Hetzner Token**: `HCLOUD_TOKEN`.
- **Tailscale OAuth**:
  - Client ID and Secret with `Devices: Write` and `tag:server` permissions.
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

Secrets are encrypted using **SOPS** and **Age**. The encrypted secrets file is located at `secrets/secrets.enc.env`. During deployment, the CI/CD pipeline decrypts this file on the target host using the `SOPS_AGE_KEY` stored in GitHub Actions secrets.
