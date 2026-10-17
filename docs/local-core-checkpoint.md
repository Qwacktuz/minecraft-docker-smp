# Checkpoint 1a: isolated local core

This is the first implementation checkpoint from `foundations.md`. Review and boot
the baseline before adding the production mod set or backup/recovery commands.

## What is implemented

- `release/local-core.json`: Minecraft 26.3, Fabric loader 0.19.5, installer 1.1.2,
  and an immutable multi-platform image digest resolved from official registries.
  Linux AMD64 and ARM64 platform digests are recorded. This is a minimal Fabric
  baseline with no feature mods or datapacks, not a production world release.
- `instances/local-a.toml` and `local-b.toml`: instance settings, separate from
  software versions and credentials. The controller rejects duplicate ports.
- `runtime/core.compose.yaml`: one game service with no global container/network
  names. Only the game port is published, always on `127.0.0.1`. No cloud, monitoring,
  backup writer, voice/webcam, or Docker-management service is included.
- `secretspec.toml`: a local profile and game scope requiring an RCON password.
  SOPS/Age encrypts generated instance credentials; SecretSpec resolves them at start.
- `bin/smp`: validates settings, renders configuration, initializes explicit blank
  local worlds, and starts/stops/inspects those instances. Local operations reject
  remote Docker contexts. State/release markers prevent accidentally recreating a
  deleted world or starting it with a changed release descriptor.

The existing root `compose.yml` and production deployment remain the legacy path.
Every new Docker command uses an explicit file and project name, preventing accidental
default-Compose selection. Do not boot a production backup in this mod-free baseline.

## Review the code

Read these files in order:

1. `release/local-core.json`: image digest and exact game/Fabric versions.
2. `instances/local-a.toml` versus `local-b.toml`: same release, distinct ports.
3. `runtime/core.compose.yaml`: loopback port, data bind, UID/GID, file-based secret.
4. `scripts/smp.py`: settings validation, curated Docker environment, state guard,
   maintenance lock, explicit initialization, SecretSpec handoff, and health gate.
5. `tests/test_local_core.py`: collision, missing-world, remote-context, credential
   isolation, rendered-resource isolation, and actual SOPS/SecretSpec roundtrip tests.

The release descriptor is hashed into each instance marker. Editing it intentionally
blocks that instance's next start. A controlled upgrade command comes later.

## Requirements

- Linux or macOS, Python 3.11+, Docker Engine/Desktop with Compose v2.20+.
- SOPS and Age (`age-keygen`), SecretSpec 0.21.0 with its SOPS provider enabled.
- Run as a normal user with Docker access. Container UID/GID match that user so
  mode-600 secret files remain readable without world-readable permissions.
- Configure `SOPS_AGE_KEY_FILE` with your existing authorized Age identity. The
  repository's `.sops.yaml` currently encrypts to its existing public recipient.
  If your identity does not match, update that recipient before initialization.
  No production secret values are needed for this exercise.
- Allow roughly 6 GB for two configured instances, plus Docker/OS overhead. On a
  smaller machine test them sequentially, then reduce the declared budgets deliberately.

Initial startup requires Internet access to obtain the pinned image and the
version-specific Minecraft/Fabric artifacts. This is not yet an offline artifact
bundle. The recorded Minecraft server checksum is provenance; this controller
does not independently download and verify every game/loader dependency yet.

Using `init-local --new-world` and starting the server accepts the Minecraft EULA
through the image's existing `EULA=TRUE` convention.

## Exercise A: validation without a Docker daemon

From the repository root:

```bash
bin/smp validate
bin/smp config local-a
bin/smp config local-b
python3 -m unittest discover -s tests -v
```

Expected: both instances validate; project names, networks, ports, data directories,
and secret-file paths differ. Both game ports bind to loopback. There is no literal
RCON password or cloud credential in rendered configuration. The roundtrip test
uses its own disposable Age key and never reads production ciphertext.

## Exercise B: real local startup

Start your local Docker engine first. Ensure your Age key is available to SOPS,
for example through your existing `SOPS_AGE_KEY_FILE` configuration.

```bash
bin/smp init-local local-a --new-world
bin/smp init-local local-b --new-world
bin/smp start local-a
bin/smp start local-b
bin/smp status local-a
bin/smp status local-b
```

Expected: each start waits for health, then confirms `data/world/level.dat` exists.
Connect with a compatible Java 26.3 client to `localhost:25566` and `localhost:25567`.
Create a recognizable change in one world and confirm it is absent in the other.
These are newly generated test worlds, not restored copies of production.

`players = []` means local whitelist enforcement is disabled; Mojang authentication
remains enabled. Add your Java profile name(s) to `players` to enable the whitelist.
No operators are automatically provisioned.

## Exercise C: preservation and refusal to overwrite

```bash
bin/smp stop local-a
bin/smp start local-a
bin/smp init-local local-a --new-world
```

Expected: your recognizable world change survives restart. Reinitialization fails
without changing the save or credentials. Then stop both instances:

```bash
bin/smp stop local-a
bin/smp stop local-b
```

Local automatic restart is disabled: startup must pass through the controller's
state guard. Each explicit `start` recreates its own container to refresh the mounted
secret file; it preserves that instance's data directory. Stop/log/status commands
do not need secret decryption. Logs show the last 100 lines via `bin/smp logs local-a`.

## Where the data goes

- `.state/instances/<name>/data`: persistent test world and server files.
- `.state/instances/<name>/instance.json`: identity, release hash, and initialization state.
- `.state/instances/<name>/runtime/rcon-password`: mode-600 runtime secret for the container.
- `.state/locks/`: per-instance maintenance locks.
- `secrets/local/<name>.enc.env`: generated SOPS-encrypted credentials, ignored by Git.

The runtime password file remains while the container needs it and is reused through
the controlled start path. It is private, but it is plaintext: Docker Compose file
secrets are file mounts, not an encrypted secret store. The image also persists its
RCON configuration inside the private data directory. Keep `.state` private and out
of Git. Do not share its contents as test output.

If initialization is interrupted, it may leave partial state; the controller refuses
to overwrite it. Inspect it before retrying. Transactional recovery and automatic
cleanup of interrupted initialization belong to the next lifecycle checkpoint.

## Report back before the next implementation

Confirm whether both instances became healthy, the worlds are independent, the
first world's change survived restart, and reinitialization was rejected. Include
the failing command and redacted error output if any check fails. Do not send Age
private keys, RCON passwords, `.state`, or decrypted environment files.

After that review, checkpoint 1b locks and qualifies the intended production mod
set; checkpoint 2 implements staged R2 restore and validated backups. The one-hour
RPO/RTO target is not yet demonstrated by this local baseline.
