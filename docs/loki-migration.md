# One-time Loki storage migration

Previous Compose releases mounted a volume at `/loki` but used the image's default
configuration, which may store logs in `/tmp/loki` inside the container. Recreating
that container can lose its history. Deployment now stops before that transition.
Fresh installations and containers already using the explicit config skip this check.

On the server, before the first deployment of this change:

1. Pause deployments. Run these commands from the application checkout in Bash.
   Inspect the existing config and mounts; confirm the actual paths before copying.

   ```bash
   docker compose exec -T loki cat /etc/loki/local-config.yaml
   docker inspect loki --format '{{json .Mounts}}'
   ```

2. Stop the log collector and Loki, then export the **actual** old data directory
   to a safe host directory. The following assumes the default `/tmp/loki` and
   the existing named volume mounted at `/loki`. Keep this export until historical
   queries work after deployment.

   ```bash
   docker compose stop alloy loki
   backup_dir="$(pwd)/backups/loki-before-migration-$(date +%Y%m%d-%H%M%S)"
   mkdir -p "$backup_dir"
   docker cp loki:/tmp/loki/. "$backup_dir/"
   ```

3. Copy into the existing volume only if it is empty. This command preserves file
   attributes and sets ownership to Loki's image UID. If the destination already
   contains data, stop and reconcile it instead of merging two stores blindly.

   ```bash
   docker run --rm --user 0 --volumes-from loki \
     -v "$backup_dir:/source:ro" alpine sh -ec '
       test -z "$(ls -A /loki)"
       cp -a /source/. /loki/
       chown -R 10001:10001 /loki
     '
   ```

4. Preserve the old config's schema history (`from`, `store`, `schema`, index
   prefix/period) in `loki/loki-config.yaml` if it differs. Existing data must remain
   readable under its original schema periods. Commit any needed schema changes
   to the branch being deployed before continuing. The new storage paths should
   remain under `/loki`.

5. After the export and volume copy succeed, mark the migration and deploy:

   ```bash
   touch .loki-storage-migrated
   ```

   Trigger the deployment workflow, or run `bash scripts/deploy.sh` with SOPS
   credentials available. Verify Loki readiness and query historical logs in
   Grafana before deleting the host export. If deployment fails, inspect logs;
   retain the export and avoid pruning the old container/image.

If any step fails before deployment, the old stopped containers still exist:
`docker compose start loki alloy` resumes their previous configuration. The marker
is an operator assertion that data was preserved, not an automatic migration.
