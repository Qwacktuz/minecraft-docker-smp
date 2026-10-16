# Proposed project foundations

Status: design proposal, 2026-10-17. This document does not change the running stack.
It builds on the quick-win branch; it does not require rewriting project history.

## Goals and operating model

Target one production Java/Fabric world on Hetzner initially, reproducible local
Docker copies, and replacement onto a new host. The user-selected objectives are
at most one hour of lost progress (RPO) and restoration of service within one hour
(RTO) after unexpected instance loss. These are targets until timed drills prove
them for the actual world size, bandwidth, mod set, and cloud capacity.

Use three explicit authorities:

- Git/release artifacts define the desired software and configuration.
- The active instance's local disk holds the current writable world.
- An encrypted Restic repository in R2 holds completed recovery snapshots.

R2 is the recovery authority, not a live shared Minecraft filesystem. Progress
since the last completed backup is not in R2. Exactly one instance may publish
production progress. Local copies are independent forks; they are not merged back.

## Small core, optional extensions

Keep Docker Compose for the game and backup tooling. Use OpenTofu for cloud
resources, minimal cloud-init for initial host access/packages, and systemd to
schedule operations and supervise the host lifecycle. Use one versioned `smp`
controller for deployment, backup, restoration, validation, and local clones.
Systemd calls the controller on Linux; local users call it directly.

The controller orchestrates existing tools. It must not implement encryption,
deduplication, a custom distributed lock, or a general infrastructure framework.

Proposed layout, to create incrementally rather than by moving everything at once:

```text
compose.yaml                    # game only; maintenance tools opt-in
compose.local.yaml              # loopback ports and local paths
compose.observability.yaml      # optional monitoring
config/                         # declarative game/mod settings
release/                        # exact versions, checksums, platform digests
instances/                      # non-secret production/local settings
secretspec.toml                 # profiles, consumers, required secret names
secrets/                        # SOPS encrypted files with distinct recipients
infra/foundation/               # durable storage/state/DNS foundations
infra/instances/                # disposable compute and instance networking
host/                           # cloud-init and systemd definitions
bin/smp                         # shared operational entry point
tests/                          # configuration and lifecycle tests
docs/                           # concise operating procedures and decisions
archive/                        # historical reference, excluded from releases
```

OpenTofu state storage and backup storage must have separate lifecycles and
credentials. Deleting an instance must never delete its repository or state
backend. Foundation creation has a documented one-time bootstrap; it must not
require the nonexistent backend it is about to create.

## Backups and validation

Schedule backup attempts every 15 minutes, even without players. This leaves
headroom within the one-hour RPO for transfer time and transient failures. Measure
the timestamp of the captured state, not just upload completion time. Alert when
the newest successful recovery point approaches 30 minutes old and escalate
before one hour; an interval setting alone does not guarantee an RPO.

Each backup records a world lineage ID, production/local role, instance ID,
release identifier, capture timestamp, included paths, and full snapshot ID.
Keep the release descriptor inside the snapshot and retain its artifacts externally.
Select by stable world identity rather than a recycled hostname. Reject incomplete
or partially successful backups for automatic recovery selection.

Use the pinned `itzg/mc-backup` implementation for online Minecraft save
coordination where possible. Invoke it as a one-shot job under the controller's
maintenance lock instead of letting an independent loop race restoration and
deployment. A systemd timer provides the cloud schedule. A stopped-server backup
uses Restic directly. Prove failure cleanup resumes saving after interrupted online
backups, and identify mod databases that require their own consistency hooks.

Distinguish three outcomes in status and records:

1. **Completed:** the backup command succeeded and metadata matches the instance.
2. **Integrity checked:** repository/data checks passed with recorded coverage.
3. **Boot tested:** a particular restored snapshot started under its matching release
   and passed application checks on an isolated machine.

Run repository structure checks daily, rotate data-read checks so all packs are
covered on a defined schedule, and perform a nightly restore-and-boot rehearsal
of the latest completed production snapshot. Record snapshot ID, release, checks,
and elapsed time outside the game server. Default `restic check` does not read all
payload data. A nightly boot test is evidence for that tested snapshot, not a claim
that every newer backup has already been boot tested. [Restic checks](https://restic.readthedocs.io/en/stable/045_working_with_repos.html).

Every actual recovery independently validates the downloaded data and gates public
access on successful startup. If the latest completed snapshot fails, report the
candidate and reason and require explicit selection of an older recovery point;
do not silently exceed the one-hour RPO.

Keep retention based on measured world growth; the existing daily/weekly/monthly
scheme is a reasonable starting point. Run destructive pruning as a separate
maintenance job, excluded from concurrent restore/verification. Never put generic
object-expiration rules over a live Restic repository. R2 bucket locks must be
tested with Restic lock deletion and pruning before adoption; a separate protected
recovery copy is preferable to blindly locking every repository object.
[R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/).

Separate a local clone's read-only storage credential from the production writer.
Restic read-only access/lock behavior must be integration-tested; if using no-lock
read operations, exclude prune for their duration. Do not promise append-only
protection from ordinary R2 read/write credentials. The production writer's ability
to damage backups remains a risk until an independent protected copy exists.

## Create, replace, restart, and destroy

Creation is an orchestrated operation, not merely `tofu apply`:

1. Resolve a completed snapshot for the requested production world and freeze its
   full ID. Resolve its matching release and obtain only the required credentials.
2. Provision a distinctly named instance; enroll it with a fresh Tailscale key.
   Bootstrap access and install pinned tools; do not start Minecraft yet.
3. Deliver runtime credentials through authenticated SSH after bootstrap. Do not
   place persistent game/storage secrets or Age private keys in cloud-init/state.
4. Restore into an empty staging directory. Verify identity, required files, data,
   ownership, available space, and release compatibility.
5. Promote the staged directory atomically on the same filesystem. Record the
   snapshot/release identity; retry safely if an earlier creation was interrupted.
6. Verify the previous production writer has stopped or been fenced through the
   cloud control plane. A timeout or missing heartbeat is not proof it stopped.
7. Start Minecraft privately and pass health plus world/mod checks. Publish/update
   player access only afterward, then enable production backup scheduling.

On ordinary restart, existing initialized state is preserved; it is not overwritten
from R2. Empty repositories, missing secrets, missing compatible releases, ambiguous
nonempty directories, and failed downloads stop creation. A new blank world requires
an explicit initialization operation and a first successful backup.

For planned replacement, pre-stage the new host, then stop the source and capture
a final cold snapshot. Restore that final snapshot, verify, cut over DNS, and retire
the old host only after successful destination backups. Old-host retention alone
does not make rollback lossless after the new host accepts writes.

Destroy normally means: lock maintenance, stop players/server, create and verify a
final backup, then remove compute. Failure to back up blocks normal destruction.
An explicit force-destroy operation may accept data loss but still cannot delete
durable storage. Unexpected instance loss restores the newest eligible completed
snapshot; it cannot recover changes that never reached R2.

## Local instances

Use the same release resolver, secrets declaration, and restore implementation.
Resolve the snapshot once; avoid selecting a moving `latest` during the operation.
Bind game/admin/RCON and optional UDP endpoints to loopback, or disable unused UDP
features. Assign a distinct Compose project, paths, and credentials. Production
backup publishing, pruning, DNS updates, and infrastructure credentials are absent.

The intended interface is small; these commands are targets, not implemented yet:

```text
smp validate
smp create production --restore latest-completed
smp replace production
smp backup production
smp verify-backups production
smp clone local --from production --snapshot <id>
smp deploy production --release <id>
smp destroy production
smp status production
```

## Unified secrets

Adopt **SecretSpec + SOPS/Age** initially:

- SecretSpec declares required keys and resolves profiles/consumer scopes.
- SOPS keeps encrypted backing files in Git; Age supplies decryption identities.
- Actual encryption recipients and storage credentials enforce access boundaries.
  SecretSpec scopes minimize delivered values but are not authorization boundaries
  if a process can also access a broader provider identity.

Use separate encrypted backing files and recipients for infrastructure provisioning,
production game/backup operation, and local read-only restoration. The production
host must not receive Hetzner/DNS administration or CI decryption credentials.
Avoid a single broad encrypted dotenv shared by every consumer.

One protected GitHub environment bootstrap Age identity is a practical first
implementation. Everything else resolves through the declared provider rather
than a long handwritten list of GitHub secrets. Bootstrap authorization remains
necessary: SecretSpec cannot decrypt SOPS by declaring a secret. Storing protected
bootstrap credentials in GitHub is a normal pattern, not inherently unprofessional.
[SecretSpec SOPS provider](https://secretspec.dev/providers/sops/).

The initial provisioning workflow uses its authorized bootstrap identity to resolve
the runtime role's credential, sends it over authenticated SSH, and installs it
root-owned for the host service. Offline recovery recipients are retained separately.
Recreation automates this handoff, not the initial establishment of account trust.

On Linux, systemd credentials deliver the runtime identity to the controller; only
resolved files needed by containers are materialized under a private runtime
directory and mounted read-only. Use supported `_FILE` inputs where available;
document environment-only exceptions. Containers should not inherit provider keys.
Local users use their authorized Age identity without needing systemd or production
write credentials. Pin SecretSpec and test that its package includes the SOPS provider.

Use GitHub OIDC for Tailscale's CI identity rather than a stored OAuth secret,
restricting issuer/subject/claims to the trusted deployment context. Provider
upgrades may be needed relative to the project's pinned Tailscale provider.
[Tailscale federation](https://tailscale.com/docs/features/workload-identity-federation).

R2 temporary credentials derive from a parent token; their existence is not proof
of direct GitHub federation. Hetzner's documented API uses bearer tokens. Keep those
credentials encrypted rather than inventing unsupported secretless authentication.
[R2 authentication](https://developers.cloudflare.com/r2/api/tokens/),
[Hetzner API](https://docs.hetzner.cloud/reference/cloud).

If removing even the CI Age bootstrap secret becomes a requirement, move the
SecretSpec backend to a managed store with supported workload authentication.
Vault/OpenBao can exchange GitHub OIDC, but self-hosting that control plane adds
backup, availability, and bootstrap work. Do not put the only secret service on the
disposable Minecraft instance. Prefer command-scoped `secretspec run` to exporting
all credentials into every later workflow step.
[SecretSpec CI guidance](https://secretspec.dev/ci/github-actions/).

## Deployment and operations

Separate validation, release creation, infrastructure operations, and application
deployment. PR jobs receive no production secrets or world data. Qualify releases
using pinned images/loader/mod artifacts; retain the exact release needed by older
snapshots. Scan dependencies and record a release SBOM, rather than maintaining an
unrelated static image inventory.

An application deployment uses a known release digest, a successful pre-change
snapshot, shared maintenance locking, graceful shutdown, and private health/world
checks before admitting players. Infrastructure replacement is an explicit operation
with a reviewed plan, not an incidental consequence of changing a whitelist.

Use a separate trusted scheduled workflow for real-world recovery rehearsals. It
must not run arbitrary PR code with production snapshot credentials. Time the full
process from declaring failure to player access, including credential resolution,
provisioning, download, verification, startup, and endpoint cutover.

Keep Docker/journald logs locally rotated. Add independent off-host checks for
game availability, backup heartbeat/age, and verification completion. Host disk and
memory plus game tick latency need monitoring even if the full dashboard stack is
disabled. Basic external checks are part of the core operational requirement.

## Tool decisions

| Tool/service | Decision | Purpose and limits |
|---|---|---|
| Docker Engine + Compose | Keep | Portable game runtime; remove hardcoded global names and separate optional profiles |
| Fabric | Keep | Existing gameplay requirement; lock loader/mod versions |
| `itzg/minecraft-server` | Keep, pin | Saves custom Java/loader bootstrap; resolve artifacts reproducibly, do not update on ordinary restart |
| Restic | Keep | Encryption, snapshots, deduplication, restore, integrity tooling |
| `itzg/mc-backup` | Keep as one-shot adapter | Reuse online save coordination; shared controller owns scheduling and maintenance exclusion |
| Cloudflare R2 | Keep | Off-host encrypted recovery repository; separate from state and instance destroy |
| OpenTofu | Keep | Cloud lifecycle with reviewed plans, backend locking, durable/ephemeral separation |
| Hetzner Cloud | Keep initially | Current target; isolate provider specifics from restore and runtime |
| Hetzner provider | Keep | Machine/firewall operations |
| Cloudflare provider/DNS | Keep | DNS and foundation resources; publish endpoint only after readiness |
| Tailscale provider | Keep/upgrade deliberately | Identity resources; tested fresh enrollment and supported OIDC configuration |
| Cloud-init provider | Keep if multipart rendering helps | Packaging convenience; native template rendering may suffice for one document |
| HTTP provider | Remove if still unused | Current runner-IP data source is commented out |
| cloud-init | Narrow | Initial packages, access, host service installation; avoid embedding the whole deployment |
| systemd services/timers | Add | Host supervision, credentials, scheduled controller operations, journal/exit status |
| Ansible | Defer | Add only when ongoing host configuration becomes complex; avoid duplicating cloud-init ownership |
| Tailscale | Keep | Private administration and CI access, explicit policies, fresh device enrollment |
| GitHub Actions | Keep | Trusted validation/release/deployment/rehearsal workflows |
| SOPS + Age | Keep | Encrypted Git-backed secrets and recovery recipients |
| SecretSpec | Add | Common declarations/profiles/consumer inputs; does not replace authentication |
| Grafana | Optional | Useful dashboards, not needed to restore or start the world |
| Prometheus | Optional monitoring bundle | Useful metrics and alerts; size/retention budgets and external availability checks required |
| Alloy | Optional with monitoring | Metrics/log collector; no unrestricted Docker socket |
| Loki | Defer from core | Rotated local logs suffice initially; add centralized history when it solves an actual need |
| Arcane | Remove from core | Duplicates the deployment control path and grants Docker authority; optional personal admin tool only |
| UFW + Hetzner firewall | Keep with explicit ownership | Cloud rules and Docker-aware host policy; UFW alone is not a container publication boundary |
| Fail2ban | Remove from minimal image unless justified | Little value on a Tailscale-only SSH path; reassess if public services need it |
| SSH/RCON | Keep, restrict | Host control and game save/admin control; RCON stays private |
| Nix/direnv | Optional developer tooling | Pin developer tools if useful; runtime/CI must not depend on an undocumented personal environment |
| ShellCheck/Actionlint/unittest | Keep | Static checks and meaningful lifecycle failure tests |
| OCI registry + release inventory | Add explicit ownership | Retained immutable release artifacts; GHCR is a natural fit with GitHub |
| External availability/heartbeat monitor | Add | Detect host loss, stale backups, and failed rehearsals when the host is gone |
| Renovate or equivalent update automation | Add after pins | Propose reviewed upgrades rather than silently updating production |
| Vim/tree/fastfetch/unzip | Trim | Install only what bootstrap/runtime actually consumes; interactive conveniences are optional |
| Swap/JVM tuning | Measure | Capacity guardrails, not substitutes for RAM/CPU; avoid unexplained tuning flags |
| Kubernetes | Defer | Revisit after recovery objectives are proven and HA requirements are concrete |

Mods are a separate gameplay/performance decision, not infrastructure requirements.
Split their exact versions into a release lock and separate feature configuration.
Keep only the gameplay features actually desired; do not remove them automatically
as part of infrastructure simplification. In particular:

- `fabric-api`, Kotlin runtime, and `balm`: retain only when required by the selected
  mods; lock the dependency graph rather than guessing what is optional.
- `spark`: useful profiling tool. Fabric exporter: use only a compatible version.
- `ferrite-core`, `lithium`, `scalablelux`, `c2me-fabric`, `servercore`,
  `alternate-current`, `clumps`, `get-it-together-drops`, `lmd`, `zfastnoise`, and
  `modernfix-mvus`: qualify performance/correctness individually; alpha resolution
  does not belong in an uncontrolled production update path.
- `carpet`, `carpet-tis-addition`, `gca`, and `luckperms`: deliberate administration
  and gameplay choices; permissions, configuration, and database state must be
  reproducible and included in consistency/recovery tests.
- `bookshelf-inspector`, `syncmatica`, `servux`, `no-chat-reports`, `packet-fixer`,
  `vanish`, `simple-voice-chat`, `webcam-mod`, `appleskin`, `armor-stands`, skull
  datapacks, and VanillaTweaks: retain based on desired player features and verified
  server/client compatibility; version and back up required persistent state.

## HA later

First deliver reproducible disaster recovery, then a warm standby and controlled
active/passive failover. Automated promotion requires reliable fencing, independent
coordination, replica freshness checks, and stable player routing. Object snapshots
alone do not provide synchronous replication or uninterrupted sessions.

Kubernetes can supervise workloads but does not make two Minecraft processes safe
writers to one world. Shared or replicated storage and access modes do not replace
application-level single-writer enforcement. Evaluate its cost only after defining
the desired outage and data-loss targets for HA.

## Implementation sequence and acceptance

1. **Reproducible local core:** exact release, separate instance settings, minimal
   Compose and SecretSpec profiles. Prove two local copies do not collide.
2. **Backup/recovery engine:** shared locks, explicit completed snapshots, staging,
   safe retries, consistency tests, and verification reports. Prove failure cannot
   start a blank world or publish a local clone as production.
3. **Cloud lifecycle:** foundation/instance split, automated runtime-secret delivery,
   fresh device identity, restore before startup, readiness before DNS. Prove a
   disposable test instance can be destroyed/recreated without deleting backups.
4. **CI/CD:** separate release, deploy, replace/destroy workflows; pinned actions,
   restricted credentials, OIDC where supported, trusted rehearsal jobs. Prove a
   whitelist change cannot replace infrastructure.
5. **Operational qualification:** backups/alerts, nightly drills, representative
   load, and full timed replacement with the real world. RPO <= 1 hour and RTO <= 1
   hour are accepted only after evidence demonstrates them.
6. **Optional monitoring/HA:** add tools against measured operational needs, keeping
   the core usable without dashboards or a management UI.

Start by qualifying existing backups and release compatibility. Preserve the
current working deployment while introducing this replacement path. Storage/account
trust setup and a Docker-capable test environment are external prerequisites; no
cloud account changes or data deletion follow merely from adopting this proposal.
