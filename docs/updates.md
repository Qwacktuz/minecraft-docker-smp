# Mods, versions and updates

Everything the server runs is pinned to an exact version, so every start gets
the same files. Most pins update themselves through pull requests against
`dev`; a few are bumped by hand. Nothing goes live until `dev` reaches `main`
and the server next starts or redeploys.

## Where each version comes from

| What | Pinned in | Source | Who updates it |
|---|---|---|---|
| Mods and datapacks | `MODRINTH_PROJECTS` in `compose.yml` (`slug:versionID # number`) | Modrinth | `scripts/pin_mods.py`; weekly PR from `.github/workflows/mods.yml` |
| Fabric loader | `FABRIC_LOADER_VERSION` in `compose.yml` | meta.fabricmc.net | `pin_mods.py`, with the mods |
| Minecraft | `VERSION` in `compose.yml` | your choice | by hand ([below](#a-new-minecraft-version)) |
| Docker images | `compose.yml`, `scripts/lib.sh` (`image:tag@sha256:digest`) | Docker Hub | Renovate PRs |
| GitHub Actions | `.github/workflows/*.yml` (commit SHA, tag in a comment) | the action's releases | Renovate PRs |
| OpenTofu providers | `infra/.terraform.lock.hcl` | the provider registry | Renovate PRs |
| Tools (OpenTofu, Python, SOPS…) | `devenv.lock` | nixpkgs | by hand: `devenv update` |
| MCA Selector (pruning) | `MCASELECTOR_VERSION` and `MCASELECTOR_SHA256` in `scripts/prune.sh` | its GitHub releases | by hand |
| SOPS on the VPS | version and checksums in `infra/cloud-init.yaml` | the SOPS GitHub release's checksums file | by hand |

You never tag anything yourself, and you never look up a Modrinth version ID or
a Docker digest by hand unless a tool can't. If you need one:

- **A Modrinth version ID** is the 8-character ID in a version page's URL
  (`modrinth.com/mod/<slug>/version/<id>`). `pin_mods.py` finds it for you.
- **A Docker digest:** `docker buildx imagetools inspect <image>:<tag>` and
  copy the `Digest:` line (the multi-arch index). Change tag and digest together.
- **A jar's SHA-256:** `shasum -a 256 <file>.jar`.

## Add a mod

1. Find its slug: the last part of `modrinth.com/mod/<slug>`.
2. Add a line under `MODRINTH_PROJECTS` in `compose.yml` with only the slug,
   e.g. `appleskin`. For a beta or alpha build write `appleskin:beta` or
   `appleskin:alpha`. A datapack takes a `datapack:` prefix.
3. Pin it. This writes the version ID and number, and keeps `[beta]`/`[alpha]`
   in the comment so later updates still allow that type:

   ```bash
   python3 scripts/pin_mods.py --write
   ```

4. If it warns that a required dependency isn't listed, add that slug too and
   run it again. The image would download it unpinned otherwise. A note that a
   mod is client-only means it may do nothing on a server; add
   `(works on the server)` to its comment if you know better.
5. Boot it on a throwaway world, then on a copy of the real one:

   ```bash
   scripts/smoke-test.sh 'rcon:list'
   ```

   ```bash
   server start local
   ```

6. Commit to `dev`, merge into `main`, then redeploy (`server start vps`, or
   Start/Redeploy on the admin page).

An unpinned slug does boot (the image fetches the newest release), which is
fine for a quick try. Pin before you commit.

**Removing a mod:** delete or comment out its line; `REMOVE_OLD_MODS` deletes
the jar at the next start. Blocks, items and entities the mod added are gone
from the world for good, so note a snapshot ID (`server backups`) first and
test with `server start local`.

## The weekly mod PR

Every Monday `mods.yml` runs `pin_mods.py --write` on `dev` and opens (or
refreshes) one PR from `mods/update` into `dev`. It is never merged
automatically. Before merging, read its warnings, then check out the branch and
run `scripts/smoke-test.sh` and `server start local`. Alpha mods and loader
bumps are the usual cause when something breaks.

Run the same thing by hand at any time: `python3 scripts/pin_mods.py` prints
what would change, `--write` applies it.

## A new Minecraft version

A world can't be downgraded once a newer version has opened it, so keep a way
back.

1. Note the newest snapshot from before the upgrade (the rollback point):

   ```bash
   server backups
   ```

2. Branch from `dev` and set `VERSION` in `compose.yml` (e.g. `"26.4"`).
3. Dry run, writing nothing:

   ```bash
   python3 scripts/pin_mods.py
   ```

   A warning `<slug>: no release-or-better fabric version for 26.4; left as is`
   means that mod hasn't been updated yet. **Comment that line out.** It keeps
   its old pin, which won't load on the new version.
4. Write the pins. This also moves the Fabric loader to the newest stable one
   for the new version:

   ```bash
   python3 scripts/pin_mods.py --write
   ```

5. Check what the script doesn't cover:
   - MCA Selector in `scripts/prune.sh` supports the version (its release
     notes), or pruning fails. Update the version and SHA-256 together.
   - The VanillaTweaks share code (`VANILLATWEAKS_SHARECODE`) has packs for it.
   - The `itzg/minecraft-server` image is recent enough. It downloads any
     version by `VERSION`, but a version that needs a newer Java needs a newer
     image (next section).
6. Boot a throwaway world, then upgrade a read-only copy of the real world:

   ```bash
   scripts/smoke-test.sh 'rcon:list'
   ```

   ```bash
   server start local
   ```

7. Optionally, run it on the real server type (the commit must be pushed):

   ```bash
   server start staging
   ```

   ```bash
   server stop staging
   ```

8. Merge into `dev`, then `main`, and start the server. The world converts at
   the first start, and the hourly backups save the new version from then on.

**To go back:** revert the commit on `main`, then `server restore <id>` with
the snapshot from step 1. Everything played since the upgrade is lost.

Commented-out mods: run `pin_mods.py` again every week or so (the weekly PR
does it too, but it skips commented lines). When a mod has a version for the
new game version, uncomment it and run `--write`.

## A new Java version

Renovate is limited to Java 25: the `itzg/minecraft-server` tags on the
`-java25` line and `eclipse-temurin` below 26 (`renovate.json`). To move:

1. Change the image tag in `compose.yml` to the `-java26` (or newer) line and
   its digest.
2. Change `JAVA_IMAGE` in `scripts/lib.sh` (used by MCA Selector).
3. Update the `itzg/minecraft-server` versioning regex and the
   `eclipse-temurin` `allowedVersions` in `renovate.json`.
4. Test as for a new Minecraft version.

## Images and everything else Renovate does

Renovate checks every Monday morning and opens PRs against `dev`. Digest and
patch updates merge themselves once CI passes; you merge minor and major ones.
The Dependency Dashboard issue lists what's pending. After an image update,
nothing else is needed: the next start pulls the new image (a few seconds
slower until the next weekly `mc-base` image build).
