# Production readiness review

**Historical baseline:** quick wins were implemented afterward; see README and Git history. Line numbers below refer to the reviewed commit.

Reviewed 2026-10-16 at commit `391236c`. Scope: tracked configuration, scripts, infrastructure, workflow, dashboards, and documentation. No live server, cloud account, decrypted secrets, or backup repository was accessed. No deployment or restore was performed.

### 1. Executive summary

**Not production-ready yet.** The choice of Docker Compose, OpenTofu, Tailscale, SOPS, and Restic is appropriate for a small SMP. The main deficiencies are in how their lifecycles interact: recovery can back up the wrong directory or select the wrong world; infrastructure replacement can lose the working disk and fail to bootstrap; releases are not reproducible; and monitoring is partly disconnected.

Positive foundations: online authentication and whitelist enforcement, no published RCON port, encrypted committed secrets, a read-only backup mount, off-host backups with retention, a Minecraft health check, and a committed provider lockfile.

Confirmed locally: shell syntax passes; Compose 5.1.2 renders with placeholder settings; OpenTofu formatting and validation pass after backend-disabled initialization. An empty `TS_IP` also passes Compose validation and removes admin-port interface restrictions. Runtime availability, mod compatibility, backup consistency, and actual host security remain unverified.

### 2. Critical blockers

#### B1. Restore leaves the backup worker attached to the old world

- **Severity:** High.
- **Location:** [restore-backup.sh:53](../scripts/restore-backup.sh), [rollback-backup.sh:37](../scripts/rollback-backup.sh), [compose.yml:276](../compose.yml).
- **Evidence/impact:** Both scripts stop only Minecraft, then rename or remove its data directory. A running backup container retains its existing Linux bind mount; renaming the host directory does not retarget that mount. It can subsequently coordinate RCON with the restored server while reading the previous world. Neither script recreates it. Backup/restore/deploy operations also have no shared maintenance lock.
- **Fix:** Serialize maintenance; let an active backup finish; stop the worker before swapping directories; explicitly recreate affected containers afterward. Restore into staging, validate it, retain the old directory, and gate success on server health plus a backup from the new data directory. On failure, preserve both directories and provide an explicit recovery path.
- **Effort:** Medium.

#### B2. Disaster recovery can restore a newly generated empty world

- **Severity:** High.
- **Location:** [how2backuprestore.md:21](../docs/how2backuprestore.md), [compose.yml:260](../compose.yml), [restore-backup.sh:35](../scripts/restore-backup.sh).
- **Evidence/impact:** The documented sequence deploys the full stack before restoring. This starts a new world and schedules its first backup after one minute. If that backup finishes before the operator restores `latest`, the selected snapshot can be the new world. Local copies would also reuse `mc-backup-worker`, `/data`, and the same backup configuration unless manually changed.
- **Fix:** Capture an explicit production snapshot ID before migration. Bootstrap a recovery host with Minecraft and scheduled backups disabled; restore and validate before enabling them. Use distinct repository credentials and identities for local/test copies. Never let a local clone prune production backups.
- **Effort:** Medium.

#### B3. Missing Tailscale IP makes admin bindings fail open

- **Severity:** High.
- **Location:** [compose.yml:294](../compose.yml), also ports 9090, 3100, 12345, 3552, and 25585.
- **Evidence/impact:** With `TS_IP=''`, Compose successfully renders these ports without `host_ip`. They are no longer restricted to the Tailscale interface. The configured Hetzner firewall is an additional barrier on the current VPS, but a homelab migration may lack it. UFW alone does not reliably protect Docker-published ports; Docker documents this interaction explicitly. [Docker firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
- **Fix:** Make the bind address mandatory, validate it as an assigned local address, and remove host publications for backends used only by other containers. Keep a loopback-only local override.
- **Example:** `"${TS_IP:?Set TS_IP explicitly}:3000:3000"`.
- **Effort:** Small.

#### B4. Server replacement is neither protected nor reliably bootstrappable

- **Severity:** High.
- **Location:** [infra/main.tf:15](../infra/main.tf), [infra/main.tf:104](../infra/main.tf), [deploy.yml:47](../.github/workflows/deploy.yml).
- **Evidence/impact:** Every main-branch deployment auto-applies infrastructure. The server permits destruction and its world is on its local disk. Separately, its bootstrap key is single-use, expires after one hour, and has no regeneration policy. The pinned Tailscale provider deliberately does not recreate invalid single-use keys by default. Replacing only the server can therefore feed cloud-init a consumed/expired key. A full destroy/apply recreates the key, but also destroys the source host. [Provider v0.29.2 source](https://raw.githubusercontent.com/tailscale/terraform-provider-tailscale/v0.29.2/tailscale/resource_tailnet_key.go).
- **Fix:** Separate infrastructure apply from application deployment; review replacement plans; protect the production server from unintended destroy; require a verified recovery point before replacement. Generate fresh bootstrap credentials for each replacement, for example through a tested `recreate_if_invalid = "always"` policy. Create and restore a second host before retiring the source.
- **Trade-off:** A short overlap costs another server temporarily, but retains a usable rollback path. `prevent_destroy` is a guardrail, not a backup or protection against manual cloud deletion.
- **Effort:** Medium.

#### B5. Concurrent runs can race on infrastructure and application state

- **Severity:** High.
- **Location:** [backend.tf:2](../infra/backend.tf), [deploy.yml:9](../.github/workflows/deploy.yml), [deploy.yml:107](../.github/workflows/deploy.yml).
- **Evidence/impact:** No backend lock configuration, workflow concurrency group, or host maintenance lock is declared. Two pushes can overlap applies, `.env` generation, and Compose changes. The host resets to the current remote `main`, not the triggering commit, so a run can deploy a later unvalidated revision.
- **Fix:** Serialize the production workflow with `cancel-in-progress: false`; add a host lock shared by deployment and recovery; deploy the exact triggering SHA. Configure and contention-test native S3 state locking with the actual R2 backend. OpenTofu supports `use_lockfile`; R2 compatibility must be exercised rather than assumed. [OpenTofu S3 backend](https://opentofu.org/docs/language/settings/backends/s3/).
- **Effort:** Small–medium.

#### B6. A restart or restore does not reproduce the same software

- **Severity:** High.
- **Location:** [compose.yml:114](../compose.yml), [compose.yml:156](../compose.yml), [deploy.yml:150](../.github/workflows/deploy.yml).
- **Evidence/impact:** Images use `stable`, `latest`, or implicit latest. Mods mostly specify project names; some explicitly allow alpha/beta versions. The loader is not pinned. Startup resolves current compatible mod releases, so restoring saved files does not guarantee replaying the original release. A whitelist change can also pull every service image. Upstream confirms automatic newest-compatible mod resolution and cleanup. [Modrinth integration](https://docker-minecraft-server.readthedocs.io/en/latest/mods-and-plugins/modrinth/).
- **Fix:** Record immutable image digests, Minecraft and loader versions, and exact mod/datapack artifacts with checksums. Test upgrades against a restored world. Associate each release with its pre-upgrade snapshot; rollback may require both the old software and old world data.
- **Trade-off:** Pins require a scheduled update process; freezing indefinitely is not a patching policy.
- **Effort:** Medium.

#### B7. Shutdown can interrupt world saving

- **Severity:** High.
- **Location:** [compose.yml:113](../compose.yml), [restore-backup.sh:55](../scripts/restore-backup.sh).
- **Evidence/impact:** No stop grace period is declared. Compose defaults to ten seconds before SIGKILL; the Minecraft image wrapper defaults to allowing sixty seconds. A busy modded world can be killed before shutdown completes. Actual save duration needs measurement. [Compose](https://docs.docker.com/reference/compose-file/services/#stop_grace_period), [Minecraft image stop behavior](https://docker-minecraft-server.readthedocs.io/en/latest/configuration/misc-options/#stop-duration).
- **Fix:** Start with `stop_grace_period: 2m`, measure shutdown under load, and coordinate it with `STOP_DURATION`. Check exit status and shutdown logs during deployment and recovery drills.
- **Effort:** Small.

### 3. Security review

- **Medium — Plaintext secret handling has unsafe failure paths.** [deploy.yml:112](../.github/workflows/deploy.yml) writes the Age key before setting permissions, decrypts directly over `.env`, and has no cleanup trap. A failure can leave the key or a truncated environment file. Use `umask 077`, a private temporary directory, cleanup traps, validation, and atomic environment-file replacement. `age.key` is not gitignored. The supplied environment key also makes writing a second key copy unnecessary if SOPS consumes it directly.
- **High impact, deliberate privilege — Arcane controls the Docker daemon.** [compose.yml:390](../compose.yml) grants the manager the host socket. `no-new-privileges` does not remove Docker API authority. Make it an optional admin profile with narrow tailnet access; its compromise should be treated as host compromise. No application exploit was established.
- **Medium — Tailscale authorization is not reviewable from this repository.** `--ssh` means Tailscale manages SSH on the tailnet address; the injected OpenSSH key and sshd hardening are not the complete authorization model. Review explicit `tag:ci` and human-admin grants and SSH rules. Remove `--advertise-exit-node` unless intentional. [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh).
- **Medium — Broad trust between containers.** Minecraft, backups, Grafana, Loki, Prometheus, and Alloy share one network. A compromised mod can reach internal management/telemetry endpoints even when their host bindings are private. Separate game/backup and telemetry networks, connecting only necessary services to both.
- **Medium — Alloy can read much of the host.** The read-only root mount exposes host files subject to effective container permissions. Read-only prevents writes, not disclosure. Prefer a constrained host metrics collector or document and restrict this trusted component. Do not casually add an unrestricted Docker socket merely to fix logs.
- **Needs verification — Credential blast radius.** Confirm separate scopes for infrastructure state, production backups, DNS, and local restore. Restic encryption does not prevent deletion by credentials that can delete repository objects. Keep an independently protected recovery copy and escrow the Restic password/Age key outside the server and CI account.

There is no first-party web application here to assess for CSRF, XSS, SSRF, or unsafe deserialization. Those checks belong to the deployed admin products and mods; their resolved versions were unavailable. No specific CVE is asserted.

### 4. Correctness and reliability

- **Medium — Player notifications never run.** [deploy.yml:143](../.github/workflows/deploy.yml) searches `docker compose ps --services` for `fabric-server`; the service is `minecraft-service`. Subsequent Compose exec commands also use the wrong identifier. Use one service-name variable consistently.
- **High — Recovery success is asserted too early.** [restore-backup.sh:91](../scripts/restore-backup.sh) prints completion after detached startup and ignores log-follow failures. It checks neither restored world identity nor Minecraft health. Failures after the directory move leave the server down without an automatic or clearly reported recovery transition.
- **Medium — Rollback destroys its current input.** [rollback-backup.sh:47](../scripts/rollback-backup.sh) removes the current world before moving the backup. Preserve that world under a new name, validate the selected backup, and check free space before restoration. Select a directory explicitly rather than silently trusting lexical latest.
- **Medium — Bootstrap readiness is confused with network presence.** [deploy.yml:66](../.github/workflows/deploy.yml) waits only for a Tailscale listing, while [cloud-init.yaml:53](../infra/cloud-init.yaml) joins before installing Docker and SOPS. Wait for successful `cloud-init status --wait` and verify prerequisites before deployment.
- **Needs verification — Live backup consistency of mod databases.** RCON save coordination is useful for Minecraft world data, but is not evidence that every mod database is quiescent. Test LuckPerms and other persistent mod state; use supported database backup hooks or a stopped-server snapshot where required.
- **Medium — “Hourly” backup policy has an idle exception.** `PAUSE_IF_NO_PLAYERS: true` suspends scheduling after an empty-server backup. Background changes can fall outside a fixed hourly recovery-point target. Disable it for a strict bound or explicitly document the exception. [Backup image behavior](https://github.com/itzg/docker-mc-backup).

### 5. Performance and scalability

The current configuration is a single stateful server. Scaling its Compose service to several replicas cannot make several processes safely share one writable world. The useful scaling paths are faster CPU/storage and tuned simulation settings for this world, or additional independent worlds with routing if the product later needs that.

- The documented default is an 8 GB host, while Minecraft permits `6656M` and has a 5 GB JVM heap. Six other services plus the OS compete for the remaining memory; they have no declared limits. This is a capacity risk, not a measured OOM finding.
- View distance 12, simulation distance 10, chunk generation, and asynchronous optimization mods need workload evidence. Measure p95/p99 tick time, GC pauses, CPU steal, disk latency, RSS, and backup duration at representative player counts. A 20 TPS target gives a roughly 50 ms tick budget.
- Establish a baseline with a small, tested mod set. Benchmark alpha optimization mods individually; their presence alone proves neither speed nor instability.
- Run backup/check/prune work with bounded CPU/I/O impact. Cache and retention sizing should follow measured world growth.
- Keep monitoring and Arcane optional for local copies. Seven always-running services are a material operational and memory cost for one SMP.

### 6. Architecture and maintainability

Compose remains an appropriate orchestrator. The valuable refactor is to separate four concerns:

1. **Release:** immutable game, loader, mod, and image versions.
2. **Instance configuration:** ports, identity, paths, memory, and environment-specific secrets.
3. **Persistent state:** complete world and required mod data.
4. **Infrastructure:** provider-specific machines, DNS, networking, and host setup.

Currently [deploy.yml:52](../.github/workflows/deploy.yml) requires Hetzner infrastructure for every application deploy. Separate provisioning and application workflows. Move remote shell logic into a versioned script with explicit inputs, shared by CI and manual operations.

Hardcoded container names, [network name `minecraft`](../compose.yml), host ports, and `$HOME/app` prevent clean multi-instance use. Parameterize them and let Compose project names isolate resources. Keep local, production, and observability overrides small.

### 7. Code quality and bad practices

- Remove the large commented-out creative server and obsolete cloud-init backup from active configuration; preserve useful examples in clearly labeled examples.
- Consolidate duplicated Restic environment/argument construction across the scripts. Pass snapshots as validated data; keep environment parsing separate from shell execution.
- [restore-backup.sh:16](../scripts/restore-backup.sh) and [test-backup.sh:15](../scripts/test-backup.sh) execute `.env` as Bash. Dotenv and shell syntax differ; spaces, `$`, or substitutions in values can break parsing or execute content. Use a consistent non-evaluating parser and validate required keys.
- `RESTIC_OPTS` is assigned in Compose and scripts but not expanded by those direct `restic` invocations. The current upstream backup loop also does not consume that variable. Treat its tuning as ineffective unless the actual pinned image demonstrates otherwise; pass documented flags/environment variables explicitly. [Upstream backup loop](https://raw.githubusercontent.com/itzg/docker-mc-backup/master/scripts/opt/backup-loop.sh).
- [deploy_local.sh:1](../archive/deploy-via-act.sh) invokes the production deployment job through `act`; it is not a local-world launcher. Rename it and document its required secrets.
- [docs/minecraft_image/Dockerfile:8](../archive/minecraft_image/Dockerfile) contains a literal `<package_name>` placeholder and is not wired into deployment. Label it an incomplete example or remove it.

### 8. Dependencies and configuration

- Keep the provider lockfile. Pin the OpenTofu CLI and GitHub actions to reviewed versions/commit SHAs, with an update workflow.
- [cloud-init.yaml:50](../infra/cloud-init.yaml) runs changing remote installation scripts. Prefer signed package repositories with explicit package policies. Verify the SOPS download and select architecture dynamically; the current binary is AMD64-only.
- Require nonempty secrets and explicit bind addresses in Compose. Validate whitelist and operator inputs before `SYNCHRONIZE` can overwrite runtime lists.
- `ignore_changes = [user_data]` means edits to cloud-init will not patch existing hosts. Establish an explicit host-update mechanism; Ansible is reasonable once needed, but does not repair recovery design by itself.
- [docs/sbom.json](../archive/supply-chain/sbom-java25-graalvm-arm64.json) describes an ARM64 `java25-graalvm` image; deployment uses mutable `stable` on a documented AMD64 host. It is not evidence about the deployed fleet or runtime-downloaded mods. Generate inventories and vulnerability scans from actual release digests and artifacts.
- Minecraft 26.3 compatibility across the configured mods, loader, datapacks, and selected image needs a boot test. No unsupported-version claim is made without that evidence.

### 9. Testing and QA

The only workflow deploys. No pull-request validation workflow or automated restore drill is present. [test-backup.sh:18](../scripts/test-backup.sh) checks metadata and lists snapshots; it does not restore or boot a world. Default `restic check` does not read all data packs. [Restic integrity checks](https://restic.readthedocs.io/en/stable/045_working_with_repos.html).

Add tests in this order:

1. **Every PR:** shell syntax/ShellCheck, Actionlint, Compose rendering with dummy settings, OpenTofu fmt/validate, and dashboard datasource-reference checks.
2. **Negative configuration:** missing bind IP or secret fails before changing services; local settings cannot select production backup write credentials.
3. **Release qualification:** boot a disposable copy of a real snapshot; validate health, world identity, permissions, critical mods, and graceful shutdown.
4. **Recovery failures:** wrong snapshot, unreachable repository, insufficient disk, interrupted restore, and concurrent maintenance. Confirm existing data remains recoverable.
5. **Scheduled integrity:** rotate data-read subsets and periodically perform a full restore-and-boot drill. Record elapsed recovery time and snapshot age.

### 10. Deployment and operations

**Observability is currently broken in several independent places:**

| Severity | Evidence | Consequence and fix |
|---|---|---|
| High | [Alloy:63](../alloy/config.alloy) uses `/var/run/docker.sock`, absent from its mounts | Docker log discovery cannot work. Prefer a read-only Minecraft log mount with a file source, or a carefully constrained Docker API proxy. |
| Medium | [Compose:167](../compose.yml) disables Fabric exporter while Alloy still scrapes it | Fresh installs have no configured Minecraft metrics producer. Re-enable only a compatible exporter, or clearly disable dependent panels and alerts. |
| Medium | [Fabric dashboard:26](<../grafana/dashboards/Minecraft Fabric-1772791686950.json>) and [Logging dashboard:26](<../grafana/dashboards/Minecraft Logging-1772791715962.json>) use foreign datasource UIDs | Provisioning creates `prometheus-main` and `loki-main`; these dashboards reference different IDs. Fix all panel and variable references. |
| Medium | [Compose:336](../compose.yml) comments out the Loki config mount | The checked-in storage configuration is unused. Mount it explicitly; verify the actual data directory and retention. |

Other operational gaps:

- No alert rules/notification receiver are declared for stale backups, disk pressure, unavailable server, missing metrics, or failed deployment. A remote uptime check is needed because all monitoring shares the server's failure domain.
- Compose and cloud-init specify no Docker log rotation. Docker's default `json-file` driver is unbounded unless overridden. Add bounded logging and verify the live daemon. Bound Prometheus storage by size as well as time; configure Loki retention. [Docker logging](https://docs.docker.com/engine/logging/configure/).
- Detached startup and a ten-second sleep are not deployment acceptance. Use bounded health checks, application-level verification, and diagnostics on failure. `restart: unless-stopped` alone does not repair a running but unhealthy service.
- [deploy.yml:155](../.github/workflows/deploy.yml) runs host-wide `docker system prune -f`. This can remove unrelated stopped containers/networks and dangling images. Remove it from the critical deployment path and retain rollback artifacts deliberately.
- The world mount is backed up; Grafana/Arcane named volumes and any UI-only state are not covered by that backup. Decide which are reproducible and which require separate protection.
- Write a migration procedure: final snapshot ID → restore on destination → isolated verification → stop/fence source → final synchronization if needed → DNS cutover → enable destination backups → retain source for a bounded rollback window. Never allow two production writers to diverge unnoticed.

### 11. Documentation and developer experience

The README overstates the implemented controls: it names Portainer although Compose uses Arcane, and describes runner-IP SSH restrictions although that firewall rule is commented out. Infrastructure docs call server keys ephemeral although `ephemeral = false`.

Missing practical material:

- A redacted `.env.example` with required variables, formats, and safe local defaults.
- Separate first deployment, existing-host deployment, restore, migration, and local-copy instructions.
- Complete GitHub environment secret/variable and Tailscale policy prerequisites.
- Tested tool versions, disk/memory assumptions, and CPU architecture support.
- A clear statement of which files and mod databases are preserved, excluded, or regenerated.
- Recovery-key escrow and emergency access when Tailscale or CI is unavailable.

### 12. User experience and ease of use

Provide a small, consistent command surface such as `validate`, `start`, `backup`, `restore`, `status`, and `logs`. A restore should display instance identity, snapshot timestamp, release version, destination path, and required free space before confirmation, then show health-based completion.

Make local copies loopback-bound, independently named, and incapable of writing/pruning production backups by default. Parameterize `APP_DIR` and data paths. Reconcile [Arcane's localhost APP_URL](../compose.yml) with its actual access URL; the functional impact needs runtime verification.

There is no custom UI warranting a separate accessibility/i18n audit. Keep CLI messages understandable without emoji/color and pair text with meaningful exit codes. If voice/webcam or player-log data is retained, document actual collection and retention; jurisdiction-specific compliance requires more context.

### 13. Top 10 improvements ranked by impact vs effort

| Rank | Improvement | Impact | Effort | Why it matters |
|---|---|---|---|---|
| 1 | Safe staged restore, explicit snapshot, worker recreation | Very high | Medium | Prevents wrong-world recovery and stale backups |
| 2 | Mandatory private bindings and required secrets | High | Small | Eliminates reproduced fail-open behavior |
| 3 | Protect replacement and refresh bootstrap credentials | Very high | Medium | Preserves data and makes migration bootstrappable |
| 4 | Workflow/backend/host locking; deploy exact SHA | High | Small–medium | Prevents competing operations and revision ambiguity |
| 5 | Pin complete releases and pair them with snapshots | Very high | Medium | Makes migration and rollback reproducible |
| 6 | Graceful shutdown and health-gated deployment | High | Small | Protects saves and prevents false success |
| 7 | Automated restore-and-boot drills | Very high | Medium | Demonstrates recoverability rather than assuming it |
| 8 | Repair telemetry; alert on backup age and host failure | High | Small–medium | Detects silent failure |
| 9 | Portable instance settings and optional admin/monitoring profiles | High | Medium | Enables safe local copies and homelab migration |
| 10 | Bound memory/log/storage growth and benchmark | High | Small–medium | Controls outages, cost, and player experience |

### 14. Quick wins

- Correct every Compose service reference to `minecraft-service`.
- Require `TS_IP` and secrets; stop publishing internal-only backends.
- Add `stop_grace_period: 2m` as an initial measured-shutdown target.
- Add workflow concurrency and `permissions: contents: read` where sufficient.
- Fix Grafana datasource UIDs and explicitly mount Loki configuration.
- Use restrictive secret-file creation, cleanup traps, and atomic replacement.
- Remove deployment-time global prune and add bounded Docker logging.
- Correct the README and add a redacted configuration example.

### 15. Long-term roadmap

**Phase 1 — Establish a recoverable service.** Fix blockers, test failure handling, define acceptable data loss and recovery time, and successfully restore production-like data onto a fresh host.

**Phase 2 — Make instances portable.** Separate release artifacts from host configuration and state. Support production and loopback-only local copies, optional observability, independent backup identities, and a documented VPS-to-homelab cutover including NAT/CGNAT and DNS considerations.

**Phase 3 — Operate against measured limits.** Track tick latency, memory, disk growth, backup age, and recovery duration. Benchmark before increasing simulation distance or player count. Schedule dependency upgrades and recovery drills.

**Phase 4 — Expand only for demonstrated demand.** Add independent worlds and routing if needed; move telemetry off-host if its resource use or failure domain justifies it. A cluster orchestrator does not by itself solve single-world state consistency.

### 16. Questions / missing information

The repository is sufficient for the findings above. A runtime review needs:

- **Scale:** expected concurrent players now and later; one shared world versus several independent worlds; world size and growth.
- **Recovery targets:** acceptable lost progress (RPO), acceptable downtime (RTO), and available migration downtime.
- **Runtime evidence:** actual image digests/mod versions, tick/GC profiles, memory/disk utilization, successful backup logs, snapshot metadata, and results of any completed restore drill.
- **Security configuration:** redacted Tailscale ACL/grants and SSH policy, GitHub environment protections, R2 credential scopes, and independent recovery-key storage.
- **Destination constraints:** homelab CPU architecture, RAM/storage, upload bandwidth, public IP/CGNAT, and whether two copies must run on one host.
- **Persistent state inventory:** active mod database backends, manually edited settings/permissions, and Grafana/Arcane changes that must survive migration.

The highest-value next learning exercise is a timed migration drill onto an isolated fresh host, including a deliberately interrupted restore and recovery from it.
