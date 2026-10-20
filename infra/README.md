# Infrastructure

OpenTofu provisions a Hetzner VPS (default `cx33`, `hel1`, Debian 13), firewall,
DNS records, and a Tailscale bootstrap key. Cloud-init installs Docker, SOPS,
Tailscale, UFW, and other host packages. Apply waits up to 15 minutes for the
server's Tailscale registration and records its node ID for cleanup on destroy.

## Access and bootstrap

- The firewall currently permits TCP 25565/24464 and UDP 25565/24454/25454.
  TCP 24464 is a legacy creative-server allowance; no active Compose service uses it.
- Public SSH is blocked; there is no active CI-runner-IP exception.
- Tailscale manages SSH on the tailnet address (`--ssh`). Review both network
  grants and SSH rules, including `tag:ci` access to the deployment user.
- The server receives `tag:server` and its configured hostname (`mc-prod` by default).
- The authentication key is single-use, expires after one hour, and creates a
  persistent device. OpenTofu refreshes consumed/expired keys on apply so a new
  VPS can enroll. Rotating this key does not unregister an already enrolled VPS.
- Apply requires one authorized device with the server hostname and `tag:server`.
  Duplicate hostnames fail validation. CI deploys using the registered IPv4
  output, so the runner does not need to resolve `mc-prod` through DNS.
- OpenTofu records the exact node ID in `terraform_data.minecraft_tailnet`.
  Its destroy provisioner removes that node through the Tailscale API before
  destroying/replacing the VPS. Missing nodes (HTTP 404) count as already removed;
  other API failures stop teardown and can be retried.
- Cloud-init advertises an exit node; approve/use that only if intentional.

## GitHub environment

Configure the `mc-prod` environment before deployment.

| Secrets | Purpose |
|---|---|
| `HCLOUD_TOKEN` | Hetzner provisioning |
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_CLIENT_SECRET` | Server enrollment keys, device lookup/removal, and CI tailnet access |
| `SSH_PUBLIC_KEY`, `SSH_PRIVATE_KEY` | Existing host/deployment key configuration |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID` | DNS management |
| `R2_ENDPOINT`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | OpenTofu state backend |
| `SOPS_AGE_KEY` | Decrypt application secrets on the host |

| Variables | Purpose |
|---|---|
| `TS_TAILNET` | Tailnet name |
| `TS_HOST` | Hetzner/Tailscale server hostname; defaults to `mc-prod` in CI |
| `USERNAME` | Deployment user; matches cloud-init |

The OAuth client must be allowed to use the server and CI tags. Authorize those
identities with explicit tailnet network and SSH policies. Network membership alone
is not the intended administrative authorization policy.

Use the existing OAuth client if it already has the required permissions. Otherwise,
open [Tailscale OAuth clients](https://login.tailscale.com/admin/settings/oauth)
and create/update a client with **Auth Keys: Write** (`auth_keys`) and
**Devices Core: Read/Write** (`devices:core`), with access to `tag:server` and
`tag:ci`. The cleanup script requests `devices:core`; the provider also needs
device read access to observe enrollment. Ensure the tailnet's tag ownership
policy allows the client to issue both tags.

Store the client ID and secret in GitHub **Settings → Environments → mc-prod →
Environment secrets** under the names above. No manually generated `tskey-auth`
key is needed, and secrets should not be pasted into chat or committed.

Runtime application settings are separately encrypted in `secrets/secrets.enc.env`.
The R2 credentials there need not be the same as the infrastructure-backend credentials.
Use the least privilege each role requires and retain recovery keys independently.

## Apply, destroy, and existing servers

Pushes to `main` apply infrastructure and then deploy. Manual **Run workflow**
defaults to `operation=apply`. To remove the entire installation, choose
`operation=destroy` and set `destroy_confirmation` to the exact hostname
(`mc-prod` by default). This removes the Tailscale device, VPS/world disk, and
other managed infrastructure; deployment is skipped. Preserve a recoverable
backup before using destroy. Do not use it simply to repair Tailscale.

The same cleanup hook runs for ordinary `tofu destroy` and server replacements
outside CI. Run from `infra`, retain this configuration and the cleanup script,
install Python 3, and export `TF_VAR_ts_oauth_client_id` and
`TF_VAR_ts_oauth_client_secret` alongside the other required variables. Supplying
these two values only via a tfvars file is insufficient for the enrollment and
cleanup subprocesses.
Do not remove the cleanup resource from configuration/state before destroying:
the provisioner and its recorded node ID are needed to remove the device.

An existing, enrolled `mc-prod` is adopted on the first successful apply. An
existing VPS that is absent from Tailscale cannot be enrolled just by creating
an API object: `tailscale up` must execute on that VPS. `ignore_changes =
[user_data]` deliberately prevents re-running bootstrap by replacing the server.
In that case apply fails at the registration wait; regain host access to enroll
it, or plan an explicit replacement after preserving the world. A new OAuth key
alone cannot repair an unreachable existing host. This change does not force
replacement or claim to recover that case automatically.

If first boot registers a device but apply fails before recording
`terraform_data.minecraft_tailnet`, its cleanup is not yet managed. Repair and
rerun apply to adopt it, or remove that specific orphan in the Tailscale console.
Out-of-band device removal also requires host re-enrollment; routine applies
retain a working device rather than churning its identity.

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
