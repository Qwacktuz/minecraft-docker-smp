# Admin runbook

What to run, in order, to do something, fix something or find out what went
wrong. Each step says where it runs. `server` is `bin/server` in the devenv
shell. "SSH in" means `ssh deployer@mc-prod` over Tailscale, then `cd ~/app`.

Background for each feature is in the [README](../README.md) and the other
files in `docs/`. Server types and prices: [web.md](web.md) and
`[vars.HOURLY_PRICES_EUR]` in `web/wrangler.toml`.

- [Everyday](#everyday)
- [Players](#players)
- [Changing things](#changing-things)
- [Backups and restores](#backups-and-restores)
- [Pruning](#pruning)
- [Troubleshooting](#troubleshooting)

## Everyday

Turning it on and off, and testing.

### Start the server for a session

*When:* Nobody is on and people want to play.

1. **Website:** Open smp.cactuz.dev/admin and press Start. You can also use GitHub (Actions → Server → Run workflow → start, on main) or the laptop:
2. **Laptop:**

   ```bash
   server start vps
   ```

3. It takes about 3 to 10 minutes. Discord posts 🟢 when it's up. Players join mc.cactuz.dev.

> The website and GitHub always deploy main. From the laptop, the current commit must be pushed, and you are asked first if it isn't on main.

### Stop the server now

*When:* Done for the night, or you want the backup taken now.

1. **Website:** Press Stop on /admin, or use GitHub's stop, or the laptop:
2. **Laptop:**

   ```bash
   server stop
   ```

3. It runs: final backup, check it reached R2, game down, 2% integrity check, then world.zip, map and website status. Then it deletes the VPS and copies to the vault. Discord posts 🔴.

> If any safety step fails, the VPS is not deleted. Otherwise you don't need to do anything: the watchdog stops it after 2 idle hours.

### Find out what's running

*When:* You don't know whether the VPS is on, or when it last backed up.

1. **Laptop:**

   ```bash
   server status
   ```

2. **Website:** smp.cactuz.dev shows up/down, players and the auto-stop countdown. /admin shows the current run's steps.

### Apply a change to the running server (redeploy)

*When:* You merged a mod, config, compose or secrets change into main while people are playing.

1. **Website:** Press Start/Redeploy on /admin, or run:
2. **Laptop:**

   ```bash
   server start vps
   ```

3. There is no restore. Players see “System update in 5 seconds”, the world is saved and containers are recreated. The game is back in about a minute.

### Let a friend start and stop the server

*When:* Someone else should be able to turn it on without you.

1. **GitHub:** Settings → Collaborators → add them with the Write role. They use Actions → Server → Run workflow.
2. **Cloudflare:** For the website: Zero Trust → Access → Applications → the smp.cactuz.dev/admin app → add their email to the Allow policy.

> Write access cannot push to main or read the secrets. Only main can use the prod environment.

### Try something on a copy of the real world

*When:* You want to test mods, config or a datapack without touching the live world.

1. **Laptop:** Check out your branch (uncommitted changes count), then:

   ```bash
   server start local
   ```

2. Connect to localhost:25565. The VPS can keep running.
3. **Laptop:** When done:

   ```bash
   server stop local
   ```

> Nothing done locally ever reaches R2. The next restore replaces it.

## Players

Whitelist, ops, griefing and bots.

### Add or remove a player on the whitelist (permanently)

*When:* A new player joins the group, or someone leaves.

1. **Laptop:** Edit MC_WHITELIST (comma-separated names):

   ```bash
   sops secrets/app.enc.env
   ```

2. **Laptop:** Commit and push to dev, then merge dev into main.

   ```bash
   git commit -am "chore: whitelist" && git push
   ```

3. **Website:** Redeploy if the server is running. Otherwise it applies at the next start.

> In-game /whitelist add works right away, but SYNCHRONIZE wipes it at the next restart. Use both when someone is waiting.

### Make someone an operator

*When:* A trusted player needs /op powers.

1. **Laptop:** Edit MC_OPS the same way, commit, push and merge to main, then redeploy.

   ```bash
   sops secrets/app.enc.env
   ```

2. **In game:** For finer permissions without full op, use LuckPerms: /lp user Name permission set <node>

### Someone griefed or stole from a base

*When:* Blocks broken or chests emptied, within the last 90 days.

1. **In game:** Click blocks to see who changed them: /lg i
2. **In game:** Find everything nearby:

   ```
   /lg search range:30 after:1d
   ```

3. **In game:** Narrow it to one player and roll it back:

   ```
   /lg rollback player:Name range:30 after:1d
   ```

4. If Ledger can't undo it (e.g. a TNT crater), restore just that area from a backup: see “Restore one area”.

> Ledger tracks blocks, containers and kills. Player inventories and positions are not in its log.

### A Carpet bot keeps the server awake

*When:* The server never auto-stops, or the website shows players overnight.

1. **In game:** See who's on: /list
2. **In game:** Remove the bot:

   ```
   /player BotName kill
   ```

3. The watchdog counts bots as players. With a bot online, only the 14-day cap stops the VPS.

## Changing things

Mods, versions, configs, settings and tokens.

### Add a mod

*When:* You want a new server-side mod from Modrinth.

1. **Laptop:** Add a line with only the slug (from modrinth.com/mod/<slug>) under MODRINTH_PROJECTS in compose.yml, e.g. `appleskin` is how an existing one looks. For a beta or alpha build write `slug:beta` or `slug:alpha`.
2. **Laptop:** Pin it. This looks up the version ID and reports missing dependencies:

   ```bash
   python3 scripts/pin_mods.py --write
   ```

3. **Laptop:** Add any dependency it warns about, run it again, then boot a throwaway world:

   ```bash
   scripts/smoke-test.sh 'rcon:list'
   ```

4. **Laptop:** Try it on a copy of the real world:

   ```bash
   server start local
   ```

5. **Laptop:** Commit to dev, open a PR dev → main, merge, then redeploy.

> An unpinned slug also boots (itzg fetches the newest release), but always pin before you commit, so every start gets the same version.

### Remove a mod

*When:* A mod is broken, unwanted or abandoned.

1. **Laptop:** Delete or comment out its line in compose.yml. REMOVE_OLD_MODS deletes the jar on the next start.
2. **Laptop:** Test on a copy first:

   ```bash
   server start local
   ```

3. Merge to main and redeploy.

> Blocks, items and entities added by the mod disappear from the world for good. Note a snapshot ID (server backups) first, in case you want them back.

### Review the weekly mod update PR

*When:* A “chore(mods): update pinned mods” PR into dev appeared on Monday.

1. **GitHub:** Read the diff and the Warnings section. CI ran validate on the branch.
2. **Laptop:** Fetch the mods/update branch and test it:

   ```bash
   git fetch origin mods/update && git checkout mods/update
   ```

3. **Laptop:**

   ```bash
   scripts/smoke-test.sh 'rcon:list'
   ```

4. **Laptop:**

   ```bash
   server start local
   ```

5. **GitHub:** Merge into dev. It goes live when dev reaches main and the server next starts or redeploys.

> These PRs never merge themselves. Alpha mods (c2me, scalablelux) and loader bumps are the usual suspects when something breaks.

### Move to a new Minecraft version

*When:* For example 26.3 → 26.4.

1. **Laptop:** Note the last backup of the old version, for a rollback:

   ```bash
   server backups
   ```

2. **Laptop:** Branch from dev, set VERSION in compose.yml, then do a dry run:

   ```bash
   python3 scripts/pin_mods.py
   ```

3. **Laptop:** Comment out every mod it warns has “no … version for 26.4”. Warned lines keep their old pin, which won't load. Then write the pins:

   ```bash
   python3 scripts/pin_mods.py --write
   ```

4. **Laptop:** Check by hand: BlueMap and Ledger support the version (pinned above), MCA Selector in scripts/prune.sh (its GitHub release notes), and the VanillaTweaks share code.
5. **Laptop:**

   ```bash
   scripts/smoke-test.sh 'rcon:list'
   ```

6. **Laptop:** The real world upgrades on a read-only copy:

   ```bash
   server start local
   ```

7. **Laptop:** Optionally, on real Hetzner hardware (commit must be pushed):

   ```bash
   server start staging
   ```

8. **Laptop:**

   ```bash
   server stop staging
   ```

9. Merge to main, then start or redeploy. The world converts on the first start.

> A world can't be downgraded. To undo: revert the commit on main, then run server restore with the ID you noted, which replaces the world with it.

### Change a mod's config

*When:* You want different settings for BlueMap, Ledger, ServerCore or any other mod.

1. **Laptop:** Copy the live file from a local copy (data/minecraft/config/…) into the repo's config/ at the same path, and edit it.
2. **Laptop:** Test, then merge to main and redeploy:

   ```bash
   server start local
   ```

> The repo copy always wins, even over newer live edits. Deleting a file from config/ doesn't reset the live one.

### Change difficulty, view distance, MOTD or memory

*When:* You want different game settings.

1. **Laptop:** Edit the environment of minecraft-service in compose.yml (DIFFICULTY, VIEW_DISTANCE, MOTD, MAX_PLAYERS, MEMORY …).
2. **Laptop:**

   ```bash
   validate
   ```

3. Merge to main and redeploy.

> MEMORY 5G sits under the container limit of 6656M on an 8 GB cx33. Raise both together, and only with a bigger type first in SERVER_TYPES.

### Change the idle auto-stop time

*When:* 2 hours is too short or too long.

1. **Laptop:** Change IDLE_MINUTES (and MAX_DAYS) in both watchdog/wrangler.toml and web/wrangler.toml.
2. **Laptop:**

   ```bash
   server watchdog
   ```

3. **Laptop:**

   ```bash
   server web
   ```

4. Commit the change.

### Add a fallback server type

*When:* Hetzner keeps selling out, or you want a different machine.

1. **Laptop:** Add the type to SERVER_TYPES in bin/server, and its hourly price to [vars.HOURLY_PRICES_EUR] in web/wrangler.toml, in the same commit.
2. **Laptop:** CI fails without the price:

   ```bash
   validate
   ```

3. **Laptop:**

   ```bash
   server web
   ```

> For a one-off start you can override without a commit: SERVER_TYPES="cx43" SERVER_LOCATIONS="fsn1" server start vps

### Renew an expired token

*When:* Tokens last about a year: R2 keys, the watchdog and web GitHub tokens, the Cloudflare deploy token.

1. **Cloudflare:** Create the new token or key with the same permissions (infra/README.md, docs/auto-stop.md, docs/web.md list them).
2. **Laptop:** Replace the value in the right file:

   ```bash
   sops secrets/infra.enc.env
   ```

3. **Laptop:** For R2_* keys, the VPS ones:

   ```bash
   sops secrets/app.enc.env
   ```

4. **Laptop:** Push the secret to the Workers again:

   ```bash
   server watchdog
   ```

5. **Laptop:**

   ```bash
   server web
   ```

6. Commit and merge the secrets file to main, so the VPS and GitHub use it.

## Backups and restores

Checking, restoring and undoing.

### List the backups

*When:* You need a snapshot ID.

1. **Laptop:**

   ```bash
   server backups
   ```

2. **Laptop:** The vault also has snapshots retention removed from R2:

   ```bash
   server backups --vault
   ```

### Prove the backups actually work

*When:* Monthly hygiene, or before a risky change.

1. **Laptop:** Read 25% of the data and verify it:

   ```bash
   server check 25
   ```

2. **Laptop:** The same for the vault:

   ```bash
   server check 10 --vault
   ```

3. **Laptop:** A full restore test from the vault alone (boots a local copy, then stops it):

   ```bash
   server drill
   ```

> A check that reports missing data can be a race with retention on a running VPS. Run it again before you worry.

### Restore the whole world to an earlier point

*When:* Something went badly wrong and Ledger can't fix it.

1. **Laptop:** Pick the ID:

   ```bash
   server backups
   ```

2. **Laptop:** With the VPS running, a safety backup is taken first:

   ```bash
   server restore <id>
   ```

3. Everything since <id> is lost. The hourly backup saves the restored world from then on.

### Restore one area

*When:* One base or region is damaged and the rest should stay as it is.

1. **In game:** Note the coordinates (F3) and dimension.
2. **Laptop:** Pick a snapshot from before the damage:

   ```bash
   server backups
   ```

3. **Laptop:** Restore every region file within 100 blocks (the VPS must be running):

   ```bash
   server restore <id> --region overworld 1200 -340 100
   ```

> A region file is 512×512 blocks, so the restore can cover more than you asked for. Changes since <id> in those files are lost.

### Undo a restore

*When:* The restore made things worse.

1. **Laptop:**

   ```bash
   server rollback
   ```

2. With the VPS running, it takes a new safety backup first, so this is undoable too. With the VPS off, it starts the VPS from the safety backup instead of the newest one.

### Look at an old state without changing anything

*When:* “What did spawn look like last month?”

1. **Laptop:** With the VPS off, this opens a read-only local copy:

   ```bash
   server restore <id>
   ```

2. Connect to localhost:25565.
3. **Laptop:**

   ```bash
   server stop local
   ```

### The main backup bucket is damaged or empty

*When:* server backups fails or lists nothing, and server check reports damage.

1. **Laptop:** Don't start the VPS. A start with no snapshots refuses, and NEW_WORLD=1 would make a new world.
2. **Laptop:** Confirm the vault has the world:

   ```bash
   server backups --vault
   ```

3. **Laptop:**

   ```bash
   server drill
   ```

4. **Laptop:** Copy the vault back into the backup bucket with rclone (vault → backups, the reverse of vault_copy in bin/server), then:

   ```bash
   server check 25
   ```

5. **Laptop:**

   ```bash
   server start vps
   ```

> Locks keep the vault's files for 30 days, so not even a stolen key can delete them. See docs/backup.md#restore-from-the-vault.

## Pruning

Deleting unused chunks safely.

### Prune for the first time

*When:* The world is large and most chunks were only flown over.

1. **Laptop:**

   ```bash
   server start local
   ```

2. **Laptop:**

   ```bash
   server prune --dry-run
   ```

3. **Laptop:** Open .cache/prune/<dimension>-delete.csv in the MCA Selector app (Selection → Import selection) and check nothing important is selected.
4. **Laptop:** Stop the local copy, then start the VPS and prune it:

   ```bash
   server stop local
   ```

5. **Laptop:**

   ```bash
   server prune
   ```

6. **In game:** Visit builds, farms and the edges of explored land.
7. **Laptop:** When it all looks right:

   ```bash
   server unpin <pre-prune-id>
   ```

### Protect an area from pruning

*When:* A farm, monument or portal hub that people rarely visit.

1. **Laptop:** Add a line to prune/protect.txt, in blocks: `overworld 1200 -340 128   # sky farm`. Dimensions are overworld, the_nether and the_end.
2. Commit and merge to main before the next prune.

### Undo a prune

*When:* Something got pruned that shouldn't have.

1. **Laptop:** Find the pre-prune snapshot:

   ```bash
   server backups
   ```

2. **Laptop:** For one area:

   ```bash
   server restore <pre-prune-id> --region overworld 1200 -340 200
   ```

3. **Laptop:** For everything (loses all changes since the prune):

   ```bash
   server restore <pre-prune-id>
   ```

### Prune every month automatically

*When:* After a few manual prunes went well.

1. **Laptop:** Set AUTO_PRUNE_DAYS=30 in prune/settings.env, commit and merge to main.
2. Every stop then prunes first, whoever presses Stop, when the last prune is more than 30 days old.

> Pre-prune snapshots stay pinned until you unpin them (PRUNE_KEEP_SNAPSHOTS=0). Set a number to keep only the newest few.

## Troubleshooting

Error messages and symptoms, and what to do.

### Start fails: Hetzner has no servers available

*When:* “Hetzner has none of these server types available…” or repeated resource_unavailable.

1. Every type in every location was sold out. Wait 10–30 minutes and start again, or widen the list for one start:
2. **Laptop:**

   ```bash
   SERVER_TYPES="cx33 cx43 cx53 cpx32 cpx42" server start vps
   ```

> A type without a price in web/wrangler.toml still starts, but shows as unpriced on /admin.

### Start fails: commit is not pushed

*When:* “commit abc1234 is not pushed to 'origin'; push it first”

1. **Laptop:** The VPS clones from GitHub, so push first:

   ```bash
   git push
   ```

2. **Laptop:**

   ```bash
   server start vps
   ```

### Age key not found

*When:* “Age key not found at ~/.config/sops/age/keys.txt”

1. **Laptop:** Restore your Age key there, or point to it:

   ```bash
   export SOPS_AGE_KEY_FILE=/path/to/keys.txt
   ```

> Without your key, only GitHub (with the CI key) can decrypt the secrets. The website and GitHub buttons still work.

### Both the VPS and a local copy run

*When:* “both the VPS and a local copy run; use 'bin/server stop local' or 'bin/server stop vps'”

1. **Laptop:** Say which one:

   ```bash
   server stop local
   ```

### Stuck waiting for Tailscale

*When:* “mc-prod did not become reachable over Tailscale SSH”

1. **Laptop:** Check the Tailscale app is running and logged in on the laptop:

   ```bash
   tailscale status
   ```

2. Check in the Tailscale admin console that mc-prod joined. If it shows as mc-prod-1, delete the stale mc-prod device.
3. **Laptop:** Run start again. It picks up the existing VPS and restores if there is no world on it yet:

   ```bash
   server start vps
   ```

### The game doesn't become healthy after a change

*When:* “Deployment did not become healthy”, or a crash after a mod or config change.

1. **VPS (SSH in):** SSH in and read the log:

   ```bash
   docker compose logs --tail 200 minecraft-service
   ```

2. Look for “Incompatible mods”, “Mixin apply failed” or “Could not find required mod”.
3. **Laptop:** Revert the commit on main (or fix it), then redeploy:

   ```bash
   git revert <sha> && git push
   ```

4. **Laptop:**

   ```bash
   server start vps
   ```

> The watchdog treats an unhealthy game as idle and stops the VPS after 2 hours. Its stop still backs up, but that backup has whatever state the broken game left.

### Stop fails: backup failed

*When:* “backup failed; the server is still running”, or ⚠️ in Discord.

1. **VPS (SSH in):** SSH in and look at the backup container:

   ```bash
   docker compose logs --tail 100 backup
   ```

2. **VPS (SSH in):** Try a backup by hand:

   ```bash
   docker compose exec backup backup now
   ```

3. **Laptop:** Once that works:

   ```bash
   server stop
   ```

> The VPS keeps running, so nothing is lost. Common causes: expired R2 keys, or a stale restic lock (the logs say so).

### Stop fails: the integrity check failed

*When:* “the backups failed their integrity check; the VPS is kept with the world on its disk”

1. The game is stopped, but the world is safe on the VPS disk. Don't delete the VPS.
2. **Laptop:** Look closer:

   ```bash
   server check 25
   ```

3. **Laptop:**

   ```bash
   server check 10 --vault
   ```

4. **Laptop:** Bring the game back while you investigate:

   ```bash
   server start vps
   ```

> Only stop again once a check passes. If the vault is fine and R2 is damaged, see “The main backup bucket is damaged or empty”.

### VPS exists but is unreachable

*When:* “a VPS exists but is unreachable; check it before destroying”

1. Open the Hetzner console (and its web console for the server) and the Tailscale admin console. Is it running, and did it join the tailnet?
2. **Laptop:** See how recent the last hourly backup is:

   ```bash
   server backups
   ```

3. **Laptop:** Only once you accept losing play since that backup:

   ```bash
   server tofu destroy
   ```

4. Delete the mc-prod device in the Tailscale admin console, then start again.

### The server didn't stop itself

*When:* Nobody played for hours and it's still running.

1. **In game:** Bots? /list. Bots count as players.
2. Open the watchdog's workers.dev URL (printed by server watchdog) to see its last decision, or check its logs in the Cloudflare dashboard → Workers → mc-idle-watchdog.
3. **GitHub:** Check the Actions tab for failed “Server stop” runs. A failed stop retries every 30 minutes.
4. **Laptop:** If the GitHub token expired, replace WATCHDOG_GITHUB_TOKEN, then:

   ```bash
   server watchdog
   ```

### It stopped while people were online

*When:* ⏹️ Auto-stop in Discord during play.

1. Read the reason in Discord. “Up for 14 days” is the cap. “Nobody online” usually means the server-list ping failed for 2 hours (crashed or unreachable game).
2. The stop backed up first. Start it again and check the logs if it was a crash.

### /admin shows 403

*When:* “Sign in through Cloudflare Access to use the admin page.”

1. **Cloudflare:** Make sure your email is in the Access policy for smp.cactuz.dev/admin, and that ACCESS_AUD and ACCESS_TEAM_DOMAIN in web/wrangler.toml match the Access app.
2. **Laptop:** If you changed them:

   ```bash
   server web
   ```

### The website's buttons refuse

*When:* “A start or stop is already running; wait for it to finish.”

1. **GitHub:** A Server run is queued or running. Watch it in Actions, or on /admin. Don't cancel a stop halfway.

### The website, leaderboard or map look old

*When:* Backups, whitelist, leaderboard or map tiles are out of date.

1. Expected: they're published only at start and stop. Hourly backups show up at the next start or stop, and the map at the next stop.
2. **Laptop:** If a stop warned “could not publish …”, it fixes itself at the next stop. To clear the map, delete map/ in the public bucket in the Cloudflare dashboard.

### healthchecks.io alerted

*When:* An email or Discord message about a failed or missing backup.

1. **VPS (SSH in):** A failed backup includes the restic log. SSH in:

   ```bash
   docker compose logs --tail 100 backup
   ```

2. “No ping for a day” while the server runs means the backup container is stuck. Recreate it:
3. **VPS (SSH in):**

   ```bash
   docker compose up -d --force-recreate backup
   ```

### Nothing posts to Discord

*When:* Starts and stops are silent.

1. **Laptop:** Check DISCORD_WEBHOOK_URL in infra.enc.env is a discord.com/api/webhooks/… URL:

   ```bash
   sops secrets/infra.enc.env
   ```

2. **Laptop:** The watchdog has its own copy:

   ```bash
   server watchdog
   ```

> Staging is always silent, by design.

### OpenTofu says the state is locked

*When:* A manual server tofu … fails on the lock.

1. **GitHub:** A start or stop is probably running. Wait for it.
2. **Laptop:** Only if you're sure nothing is running (the error prints the lock ID):

   ```bash
   server tofu force-unlock <lock-id>
   ```

### The CI Age key leaked

*When:* SOPS_AGE_KEY may have been exposed.

1. **Laptop:** Remove the GitHub recipient from .sops.yaml, then re-encrypt:

   ```bash
   sops updatekeys -y secrets/*.enc.env
   ```

2. **Laptop:** Rotate every token in both secrets files, then commit.
3. **GitHub:** Delete SOPS_AGE_KEY in the prod environment (or replace it with a new key added to .sops.yaml).

> The vault stays safe either way: its bucket lock refuses deletes for 30 days.

## Server types and prices

From `[vars.HOURLY_PRICES_EUR]` in `web/wrangler.toml`. `bin/server` tries
the types top to bottom, each in hel1, fsn1, then nbg1, and moves on only when
Hetzner returns `resource_unavailable`.

| Order | Type | €/hour | 50 h month | Full month (730 h) |
|---|---|---:|---:|---:|
| 1st | cx33 | 0.0144 | 0.72 | 10.51 |
| 2nd | cx43 | 0.0264 | 1.32 | 19.27 |
| 3rd | cx53 | 0.0481 | 2.41 | 35.11 |
| 4th | cpx32 | 0.0489 | 2.45 | 35.70 |
| not used (ARM, untested) | cax21 | 0.0176 | 0.88 | 12.85 |
| not used (ARM, untested) | cax31 | 0.0344 | 1.72 | 25.11 |

The mc-base image costs about €0.03 a month while it exists. The 14-day
uptime cap limits a forgotten cx33 to about €4.84.
