# Infrastructure

OpenTofu provisions a Hetzner VPS (default `cx33`, `hel1`, Debian 13), firewall,
DNS records, and a Tailscale bootstrap key. Cloud-init installs Docker, SOPS,
Tailscale, UFW, and other host packages.

## Access and bootstrap

- The firewall currently permits TCP 25565/24464 and UDP 25565/24454/25454.
  TCP 24464 is a legacy creative-server allowance; no active Compose service uses it.
- Public SSH is blocked; there is no active CI-runner-IP exception.
- Tailscale manages SSH on the tailnet address (`--ssh`). Review both network
  grants and SSH rules, including `tag:ci` access to the deployment user.
- The server receives `tag:server` and its configured hostname (`mc-prod` by default).
- The authentication key is single-use, expires after one hour, and creates a
  non-ephemeral device. It is not automatically refreshed for server replacement
  by this configuration. Generate a fresh key when replacing the host.
- Cloud-init advertises an exit node; approve/use that only if intentional.

## GitHub environment

Configure the `mc-prod` environment before deployment.

| Secrets | Purpose |
|---|---|
| `HCLOUD_TOKEN` | Hetzner provisioning |
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_CLIENT_SECRET` | Server-key provisioning and CI tailnet access |
| `SSH_PUBLIC_KEY`, `SSH_PRIVATE_KEY` | Existing host/deployment key configuration |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID` | DNS management |
| `R2_ENDPOINT`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | OpenTofu state backend |
| `SOPS_AGE_KEY` | Decrypt application secrets on the host |

| Variables | Purpose |
|---|---|
| `TS_TAILNET` | Tailnet name |
| `TS_HOST` | Destination Tailscale hostname |
| `USERNAME` | Deployment user; matches cloud-init |

The OAuth client must be allowed to use the server and CI tags. Authorize those
identities with explicit tailnet network and SSH policies. Network membership alone
is not the intended administrative authorization policy.

Runtime application settings are separately encrypted in `secrets/secrets.enc.env`.
The R2 credentials there need not be the same as the infrastructure-backend credentials.
Use the least privilege each role requires and retain recovery keys independently.

## Local validation and administration

Backend-free validation needs no cloud credentials:

```bash
tofu init -backend=false -lockfile=readonly
tofu fmt -check
tofu validate
```

For actual administration, provide the required `TF_VAR_*` variables from
`variables.tf` and initialize the R2 backend using your private backend configuration.
Keep credential files out of Git. Review `tofu plan` before applying changes.

The deployment workflow still auto-applies infrastructure. `prevent_destroy` is
currently false, world data lives on the VPS disk, and backend locking is not yet
configured. GitHub concurrency reduces overlapping workflow runs; it does not lock
out manual OpenTofu runs. Do not use destroy/apply as a routine migration procedure.

`ignore_changes = [user_data]` means editing cloud-init does not patch an existing
host. Bootstrap currently downloads an AMD64 SOPS binary. Host replacement,
ARM support, and ongoing OS configuration require additional work.

See [backup and restore](../docs/how2backuprestore.md) before any replacement.
