# Cloud Portal production rename — 12 October 2026

## Current state and evidence

This supersedes the former `proxmox-billing`, `/opt/billing`, `billing.service`, `billing_project` and `billing_db` operating names. Evidence is user-provided terminal output on 10 and 12 October 2026, not direct agent SSH access.

| Component | Verified value |
|---|---|
| Repository | john-selwyn/cloud-portal |
| Deployment branch | codex/windows-rdp |
| Deployed application commit at cutover | ecbfd6d (pushed to origin) |
| Tested refactor branch | refactor/cloud-portal-internals |
| VM200 | 10.50.0.22; hostname cloud-portal; Linux user ict-tech |
| Working directory | /opt/cloud-portal |
| Service | cloud-portal.service; enabled at boot |
| Gunicorn | /opt/cloud-portal/venv/bin/gunicorn; 3 workers; 127.0.0.1:8001; cloud_portal.wsgi:application |
| Django project / app / label | cloud_portal / portal / portal |
| Templates / assets | portal/templates/portal; portal/static/portal |
| Collected assets | /opt/cloud-portal/staticfiles |
| Nginx site | /etc/nginx/sites-available/cloud-portal; enabled site cloud-portal |
| Public portal | https://proxmoxportal.dyndns.org |
| VM300 | 10.50.0.23; hostname ictdatabase; Linux user ictroot |
| PostgreSQL | 18.6; matching pg_dump 18.6 |
| Portal database / login role | cloud_portal_db / cloud_portal_user |
| Database owner | postgres (preserved) |
| Eight application table owners | cloud_portal_user (role identity preserved) |
| Provisioner database | vps_portal (not renamed) |
| PostgreSQL access file | /etc/postgresql/18/main/pg_hba.conf |
| Native backup script | /usr/local/sbin/postgresql-native-backup.sh |
| Test code checkout | /opt/cloud-portal-rename-test |
| Test database | cloud_portal_rename_test_20261010 |

The active PostgreSQL rule is:

```text
host cloud_portal_db cloud_portal_user 10.50.0.22/32 scram-sha-256
```

A temporary restore-test rule also allows the same role and source host to connect to `cloud_portal_rename_test_20261010`. VM200's test .env DB_USER was updated after the role rename. Keep the test environment isolated from provider/provisioner credentials.

## What was changed and verified

1. Copied the deployment to /opt/cloud-portal, rebuilt its virtual environment and switched Gunicorn/Nginx. Old /opt/billing was retained for recovery.
2. Renamed VM200's hostname to cloud-portal; /etc/hosts keeps billing-server as a compatibility alias for 127.0.1.1.
3. Renamed the GitHub repository and updated VM200's origin URL. Branding commit: 21dcad5.
4. Prepared an isolated worktree, restored a production dump into a separate PostgreSQL database and checked tables/migrations.
5. Renamed billing_project to cloud_portal, billing to portal, template/static namespaces and Python references.
6. Retained the app label billing temporarily, then deliberately relabelled migration history/content types and changed code/migration references together in the restored database.
7. Passed all 146 existing Django tests on a temporary in-memory SQLite database; git diff --check was clean. SQLite does not establish PostgreSQL concurrency behavior.
8. Stopped the portal and refreshed its protected cutover dump before live schema changes.
9. In a guarded PostgreSQL transaction, renamed eight tables and eight ID sequences, preserved row counts, relabelled eight content types without changing their IDs, and changed eleven django_migrations records from billing to portal.
10. Renamed billing_db to cloud_portal_db and billing_user to cloud_portal_user. The password was verified as SCRAM before role renaming; password, role identity, grants and ownership were preserved.
11. Installed the prepared PostgreSQL rules and native backup script; access-rule parsing returned zero errors and pg_reload_conf() returned true.
12. Fast-forwarded VM200 to ecbfd6d, installed its prepared .env/service and verified the real database/role with SQL.
13. Django check passed, migrate --plan showed no operations, 134 static files were collected, the service was active, and local /register/ returned HTTP 200.
14. Pushed codex/windows-rdp to ecbfd6d.
15. Ran the updated native backup's backup/validation portion without its retention deletion section. It completed successfully at /mnt/postgresql-backup/native/2026-10-12_01-54-47.

Live counts at the cutover: customers 5, invoices 26, orders 26, payments 23, subscriptions 17, plans 2, power operations 19, Xendit checkouts 23. These are dated observations, not permanent expected counts.

Browser verification after the internal cutover remains pending in this record. The earlier branding-only cutover had a successful user browser check. A new real payment, VPS provisioning run and service reboot were not tested by the internal rename.

## Routine verification commands

On VM200 as ict-tech:

```bash
cd /opt/cloud-portal
git branch --show-current
git rev-parse HEAD
./venv/bin/python manage.py check
./venv/bin/python manage.py showmigrations portal
systemctl is-active cloud-portal.service nginx
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -H 'Host: proxmoxportal.dyndns.org' http://127.0.0.1:8001/register/
```

On VM300 as ictroot:

```bash
sudo -u postgres psql -X -P pager=off -d postgres -c "SELECT line_number, error FROM pg_hba_file_rules WHERE error IS NOT NULL;"
sudo -u postgres psql -X -d cloud_portal_db -c "SELECT current_database(), count(*) FROM django_migrations WHERE app = 'portal';"
```

All listed commands are read-only. Expected: active services, HTTP 200, no HBA parsing errors and 11 existing portal migration records. New features may add later migrations.

For a future code-only deployment, first preserve/review working-tree changes and the pre-update commit, then use the intended branch and run checks. Collect static assets when needed. Restarting cloud-portal.service briefly interrupts requests. Never replay old schema relabelling against the already renamed database.

## Resolved restore-test access error

Problem: pg_restore from VM200 failed with no pg_hba.conf entry for billing_user and the new test database. The connection was denied before any restore wrote data.

Cause: the original host rule allowed billing_db only. Diagnostics on VM300: SHOW hba_file and pg_hba_file_rules, including database/user/source/auth_method/error.

Verified fix: backed up pg_hba.conf, appended a rule restricted to the test database, billing_user and 10.50.0.22/32 with scram-sha-256, checked for zero parsing errors and called pg_reload_conf(). Repeating the restore with --single-transaction --exit-on-error succeeded. After role rename the rule uses cloud_portal_user. Do not broaden this rule to all databases or hosts.

## Recovery material

| Host | Retained material |
|---|---|
| VM200 | /root/cloud-portal-rename.LWVL9C — original service/Nginx configuration and hostname/hosts backups |
| VM200 | /root/cloud-portal-app-rename.LK9gvF — env.before, service.before, staged env.next/service.next |
| VM200 | /opt/billing — earlier deployment copy; stale after the internal rename, not a compatible standalone rollback |
| VM300 | /root/cloud-portal-db-rename.C66Dy6 — pg_hba.conf.before, backup-script.before and candidates |
| VM300 | /var/lib/postgresql/cloud-portal-cutover.071qxP/billing_db.dump — refreshed while portal stopped |
| VM300 | /var/lib/postgresql/cloud-portal-cutover.071qxP/globals.sql — protected pre-rename roles snapshot |
| NAS | /mnt/postgresql-backup/native/2026-10-12_01-54-47 — new cloud_portal_db.dump, vps_portal.dump and postgres-globals.sql |

These files contain sensitive configuration or customer records. Do not publish their contents, copy secrets into docs or overwrite the NAS's restricted permissions.

Recovery is coordinated, not a service-only restart. The old code expects billing_* tables and old app labels. A reviewed reversal must stop all portal writers, preserve current post-cutover data, reverse table/sequence names and metadata labels while preserving IDs, reverse database/role names, restore matching HBA/backup/application configurations and deploy matching old code. The reversal was not executed or tested in this session.

For dump-based recovery, restore a selected dump into an isolated database first, verify records/permissions and reconcile any transactions since the snapshot before promotion. A wholesale globals.sql restore may affect unrelated PostgreSQL roles; do not run it blindly on the shared server. Historical pre-cutover dumps use the old names; new dumps use portal_* metadata and cloud_portal_user. No routine reset, fake migration or destructive database replacement is part of this rename.

## Remaining limitations and follow-up

- Confirm browser login, existing VPS, order and invoice views after the internal cutover.
- NAS archive listing succeeded; a fresh restore of the 12 October post-cutover NAS dump has not been tested. The 10 October pre-cutover dump was restored and validated.
- The updated script's scheduled execution and retention run were not reverified. Its normal final step removes immediate backup directories older than 30 days; the manual verification omitted deletion.
- Existing database index/constraint names can still contain billing_; renaming tables/sequences did not rename those objects.
- CHECKOUT_SALT remains billing.order-review to preserve existing signed reviews. BILLING_API_SECRET and billing_order_id remain integration compatibility identifiers.
- Legacy backup folders/files and historical documentation retain old names intentionally.
- Repository main was not merged or deployed. Use the verified deployed branch, not the default branch, when continuing work.
- GitBook Current System Status remained stale: attempted writes returned HTTP 403 (requires user authentication). This GitHub record is the verified handoff pending GitBook synchronization.
