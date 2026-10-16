# Inactive reference material

Nothing here is loaded by Compose, cloud-init, deployment, or validation workflows.
Files are retained for reference rather than deleted. Do not deploy these examples
without reviewing their assumptions and updating their versions.

| Path | Original location / reason |
|---|---|
| `supply-chain/sbom-java25-graalvm-arm64.json` | `docs/sbom.json`; historical ARM64 image inventory, not the deployed release |
| `minecraft_image/` | `docs/minecraft_image/`; incomplete custom-image experiment |
| `mc-configs/` | `mc_unused/`; unmounted permission/Carpet/bootstrap experiments |
| `mc-config-notes.txt` | Commented configuration notes removed from Compose |
| `creative-server.yml.example` | Disabled creative-server block removed from Compose |
| `cloud-init-rootless.yaml` | `infra/cloud-init.yaml.bak`; superseded rootless bootstrap |
| `deploy-via-act.sh` | `scripts/deploy_local.sh`; invokes production CI, not a local instance |
| `static/tux.jpeg` | Unreferenced image; the active server icon remains in `static/` |
| `how2vibe.md` | Personal tool note, unrelated to operation |

The historical SBOM remains large. Moving it clarifies ownership but does not
reduce clone size or rewrite Git history. License material remains in `docs/LICENSE`.
