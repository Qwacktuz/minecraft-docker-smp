# Mod configs in Git

At every start the game container copies this folder into the world's
`config/` folder (`/data/config`), and **the copy here wins**, even when the
live file is newer (`SYNC_SKIP_NEWER_IN_DESTINATION: false` in `compose.yml`).

- Only the files in this folder are replaced. Every other mod config stays as
  the world has it, so a mod's config is only managed here once its file is.
- Deleting a file here doesn't delete the live copy; the world keeps the last
  version. Remove it in the world too if you want the mod's defaults back.
- Commit only configs you have deliberately set, never the live databases
  (e.g. `luckperms/`) or per-world data.
- Test a change with `server start local` (or `scripts/smoke-test.sh` for a
  fresh world) before it reaches `main`.

This README is copied too, as `config/README.md` in the world; it's harmless.

| File | Mod | What is set |
|---|---|---|
| `bluemap/core.conf`, `bluemap/webapp.conf`, `bluemap/webserver.conf` | BlueMap | download accepted, 1 render thread, own web server off, browser-side decompression ([docs/map.md](../docs/map.md)) |
| `ledger.toml` | Ledger | logs older than 90 days are purged (`autoPurgeDays`) |
| `meowantixray.yml` | Meow Anti-Xray | engine mode 1, Nether hidden up to y=128, End off |
