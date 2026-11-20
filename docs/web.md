# The web app (smp.cactuz.dev)

A SvelteKit app in `web/`, running as a Cloudflare Worker. It doesn't replace
`bin/server`: it shows what's going on and presses the same buttons.

- **`/`, public:** is the server up, who's online (names and skin heads), how
  long until the idle auto-stop, how to join, and the `world.zip` download. It reloads the
  numbers every 30 seconds (`/api/status`).
- **`/admin`, behind Cloudflare Access:** Start/Redeploy and Stop buttons, the
  Server workflow's recent runs with their steps as they go, and the backup list.

## How it works

```
browser ──► smp.cactuz.dev (Worker: web/)
              ├─ DNS + server list ping   watchdog/src/minecraft.js (shared with the watchdog)
              ├─ STATE (Workers KV)        the watchdog's state: up since, last busy
              ├─ GitHub API                dispatch server.yml on main; list runs and steps
              └─ WEB (R2: mc-smp-web)      backups.json, written by the VPS
```

- **Start and Stop** start the GitHub "Server" workflow on `main`, exactly like
  the "Run workflow" button and the watchdog. The workflow runs `bin/server`, so
  there is still one code path. The Worker refuses while a run is in flight.
- **The backup list** can't come from restic in a Worker, so the VPS publishes it:
  `scripts/publish-status.sh` runs `restic snapshots --json | snapshots.py --json`
  and uploads `backups.json` to the `WEB_BUCKET`. `bin/server` calls it after
  every start and after the final backup on stop. Hourly backups in between show
  up at the next start or stop.
- **Auth** is Cloudflare Access in front of `/admin*`. The Worker also verifies
  Access's signed `Cf-Access-Jwt-Assertion` header (`web/src/lib/server/access.ts`)
  and returns 403 without it, so a route that skips Access still can't press Stop.

## Setting it up (once)

1. **Cloudflare Access.** Cloudflare dashboard → Zero Trust → Access →
   Applications → Add → Self-hosted:
   - Domain `smp.cactuz.dev`, path `admin` (this covers `/admin/*` too).
   - A policy: Allow, with the admins' emails (or a GitHub login method).
   - From the application's overview, copy the **Application Audience (AUD) tag**,
     and from Zero Trust → Settings → Custom Pages your **team domain**
     (`<team>.cloudflareaccess.com`). Put both in `web/wrangler.toml`
     (`ACCESS_AUD`, `ACCESS_TEAM_DOMAIN`) and commit; neither is secret.
2. **The Cloudflare token.** Reuse `WATCHDOG_CLOUDFLARE_TOKEN`
   ([auto-stop.md](auto-stop.md)), and add these permissions to it:
   Account → **Workers R2 Storage** → Edit, and Zone → **Workers Routes** → Edit
   for `cactuz.dev` (for the custom domain).
3. **A GitHub token for the web app**, separate from the watchdog's so each can
   be revoked alone: fine-grained, only `minecraft-docker-smp`, **Actions → Read
   and write**. Add it to the infra secrets as `WEB_GITHUB_TOKEN`:

   ```bash
   sops secrets/infra.enc.env
   ```

4. **The backup list.** Add `WEB_BUCKET=mc-smp-web` to the app secrets
   (`sops secrets/app.enc.env`). The R2 key there (`R2_ACCESS_KEY_ID`) must be
   allowed to write that bucket, like it is for `PUBLIC_WORLD_BUCKET`.
5. **Deploy:**

   ```bash
   server web
   ```

   It builds `web/`, creates the `mc-smp-web` bucket if needed, deploys the
   Worker on `smp.cactuz.dev`, and stores `WEB_GITHUB_TOKEN` as its secret.

The watchdog's idle rules are in both `watchdog/wrangler.toml` and
`web/wrangler.toml` (`IDLE_MINUTES`, `MAX_DAYS`); change them together.

## Working on it

```bash
cd web
npm install
npm run dev        # http://localhost:5173, in workerd with local KV and R2
npm run check      # svelte-check (types)
npm test           # Vitest: status and run formatting
```

In `npm run dev` there's no Access, so `/admin` is open and signed in as
`dev@localhost`. Local KV and R2 start empty (the page shows "no backup list
yet"). For the live ping against a local copy, run `server start local` and put
`HOST=localhost` in `web/.dev.vars` (git-ignored). The dev server runs in Node,
so it pings over `node:net` (`web/src/lib/server/ping-node.ts`); the deployed
Worker uses `cloudflare:sockets`; for the runs list and buttons, add a
`GITHUB_TOKEN=` there too (a token that can only run this repository's
workflows; the buttons really start the VPS).

`validate` (and CI) runs `npm ci`, the type check, the tests and the build.

Files:

- `web/src/routes/+page.svelte`, `+page.server.ts`, `api/status/`: the public page.
- `web/src/routes/admin/`: the admin page, its start/stop form actions, and
  `api/runs/` (polled every 5 s while a run is going).
- `web/src/hooks.server.ts`, `web/src/lib/server/access.ts`: the Access check.
- `web/src/lib/status.ts`, `runs.ts`: what the pages show (pure, tested).
- `web/src/lib/server/`: KV, R2 and GitHub reads.

**Player names** come from the server list ping's `players.sample`, the same list
the multiplayer screen shows: vanilla sends at most 12, players who turned off
"Allow Server Listings" are left out, and vanished players (the Vanish mod) don't
appear. So the page can name fewer people than it counts. The skin heads load
from mc-heads.net in the viewer's browser.
- `watchdog/src/minecraft.js`: DNS, ping and GitHub calls, shared with the watchdog.
