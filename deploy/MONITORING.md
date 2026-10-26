# Infrastructure monitoring

Status: integrated with the new admin UI for review, 15 October 2026; no production deployment or live collector verification yet.

## Live verification update — 15 October 2026

This supersedes the development status above: user terminal output confirms VM200 `/opt/cloud-portal` deployed `cfb3e3d`, Django checks passed, static files collected and cloud-portal.service active. Service User ict-tech, Group www-data. User explicitly approved direct rollout without preview.

Explicit CA trust verified from VM200: vps01 `https://10.50.0.10:8006` with `/opt/cloud-portal/monitoring-ca/vps01-ca.pem`; test-1 `https://test-1.lab.local:8006` with `/opt/cloud-portal/monitoring-ca/test1-ca.pem`. Both unauthenticated version requests returned HTTP 401, TLS verification 0. Local hostname resolves to 10.50.0.11. Public CA fingerprints compared with trusted host console output.

Dedicated `cloud-monitor@pve!portal` tokens created separately on both hosts with privilege separation and PVEAuditor on both user and token. Private token files transferred with mode 600 into mode-700 var/monitoring-setup; configuration script backed up existing .env there and added host metadata and token variables without printing secrets. .env mode 600. Token files and environment backups must never be committed or shared.

First collection reported partial; exact cause remains unconfirmed. Later endpoint diagnostics all succeeded, and repeated collect_monitoring reported both hosts connected with empty errors arrays: vps01 24 VM/template records, test-1 20. Initial failure was not proven to be a permissions error. No privilege expansion was performed.

Known limitation confirmed by live output and Proxmox source: storage content endpoints can return HTTP 200 and ACL-filtered empty backup lists under PVEAuditor. Both NAS listings returned zero visible entries despite independently verified archives. Missing visible records must display Not verified, never No archive found. This correction includes regression coverage for empty and partially filtered successful responses. Backup schedules and API task results are separate signals; a connected host is not proof of verified backup coverage. Do not grant Datastore.AllocateSpace, Datastore.Allocate or VM.Backup merely to expose monitoring metadata. A separate least-privilege metadata export remains future work if archive coverage is required.

After this correction, 19 monitoring tests passed. Corrective commit deployment, browser owner access and scheduled collection still require live verification. Notifications remain off.

## What the page does

Owner/superuser route: `/management/monitoring/`, linked from the Management overview. Ordinary staff and customers cannot access infrastructure inventory in this first version. It uses the existing separate Management session and does not alter staff accounts.

Shows host CPU/memory/uptime, root and storage usage, virtual machines/templates, scheduled-backup selection, newest archive per VM and recent backup-task results. Readings are saved snapshots. Browser refresh every minute reads the snapshot only, with automatic refresh paused while filtering VMs or while the tab is hidden.

Freshness limit is three minutes; missing/corrupt data shows an unconnected state, failed or incomplete checks are visible, and stale hosts never count as currently reporting. Archive freshness threshold is 36 hours. Storage warnings begin at 80%; inactive storage also needs review. NAS storage entries may refer to one shared filesystem and are never summed. Pool-based schedule membership is not guessed.

No notifications, remote commands, VM control, IP/NAT/firewall edits, schema migrations or new dependencies. VM running does not establish guest-service health. This first version does not collect guest services, native PostgreSQL dump status, certificate expiry, website availability, individual disk exclusions or historic resource trends.

## Connection configuration — proposed, not executed

Create a dedicated monitoring user and privilege-separated API token on each Proxmox host. Give both the backing user and token `PVEAuditor` on `/` with propagation, or an equivalently scoped read-only role covering node, VM and backup storage reads. Use no provisioning/admin token. API calls are exclusively GET: node status, storage, qemu inventory, tasks, cluster backup jobs, storage backup contents. No task logs, passwords or guest config are retrieved.

Official references: [Proxmox read-only monitoring tokens](https://github.com/proxmox/pve-docs/blob/master/pveum.adoc), [Proxmox API](https://pve.proxmox.com/pve-docs/api-viewer/).

Verify the host's certificate issuer through a trusted administrative connection, install the verified CA certificate on VM200, and use an HTTPS hostname/IP covered by that certificate. Never disable certificate verification or retrieve credentials through chat. `ca_bundle` accepts a local CA file path; otherwise system certificate trust is used. No new public exposure is needed.

Example `.env` host metadata (origins are illustrative placeholders, not verified DNS records):

```dotenv
MONITORING_HOSTS_JSON='[{"name":"vps01","node":"vps01","url":"https://CUSTOMER_HOST_CERTIFICATE_NAME:8006","token_id_env":"MONITORING_VPS01_TOKEN_ID","token_secret_env":"MONITORING_VPS01_TOKEN_SECRET","ca_bundle":"/opt/cloud-portal/monitoring-ca/vps01-ca.pem"},{"name":"test-1","node":"test-1","url":"https://MANAGEMENT_HOST_CERTIFICATE_NAME:8006","token_id_env":"MONITORING_TEST1_TOKEN_ID","token_secret_env":"MONITORING_TEST1_TOKEN_SECRET","ca_bundle":"/opt/cloud-portal/monitoring-ca/test1-ca.pem"}]'
MONITORING_SNAPSHOT_PATH=/opt/cloud-portal/var/monitoring.json
```

Set the four referenced token variables privately on VM200. The host list contains only environment-variable names, not secret values. Do not commit `.env`, CA directories with private material, or snapshots. `var/` is ignored. Restrict the `.env` and snapshot directory to the portal service account.

Identify the current service account on VM200 before installing a collector unit:

```bash
systemctl show cloud-portal.service -p User -p Group -p WorkingDirectory
```

Create `/opt/cloud-portal/var` for that account, mode 750. Run collection as the same account that reads the page. Atomic file replacement uses a mode-600 temporary file and writes only an allowlist of metrics/identifiers; raw API responses and authorization headers are not saved.

From `/opt/cloud-portal`, as that service account:

```bash
./venv/bin/python manage.py collect_monitoring
```

Expected: each host prints `connected`. Missing credentials, TLS failure or denied permissions save a sanitized partial/unavailable snapshot and produce a nonzero exit. Inspect source error codes locally rather than publishing secrets. Collection cannot send messages or change guests.

Open Management → Infrastructure monitoring. Confirm both hosts report, compare readings with Proxmox, verify scheduled inclusions/exclusions, and check the newest archives/tasks. A token with insufficient VM/storage scope can hide items; ensure the role actually covers the intended full inventory.

## Collector schedule

Review and replace the service-user placeholder in the included unit before installation. Keep current application `.env` and other workers unchanged. Proposed VM200 install, not executed by this development task:

1. Install the edited service as `/etc/systemd/system/cloud-portal-monitoring.service` and timer as `/etc/systemd/system/cloud-portal-monitoring.timer`.
2. Run `sudo systemctl daemon-reload`, then `sudo systemctl enable --now cloud-portal-monitoring.timer`.
3. Inspect `systemctl list-timers --all cloud-portal-monitoring.timer` and `sudo journalctl -u cloud-portal-monitoring.service -n 30 --no-pager`.

The timer waits one minute after a completed collection. A systemd service cannot overlap itself. The 180-second collection timeout makes a hung collector visible as stale data; review collection duration against host/storage count.

## Deployment

UI baseline: `design/management-refinement` at `b579ebdc8199938a9ec3f6d9ae77d5b89809a3eb`. Latest documented production is `b899140`; the Management UI and this monitoring addition remain review work. Before later rollout inspect clean tracked files and revision; preserve newer unrelated work. No database migration is required. Run application checks and collectstatic for the new stylesheet/script, then restart `cloud-portal.service` in a planned brief application restart window. Deploying without connection settings shows the honest empty state; it never fabricates live health.

First deploy and inspect owner access/empty state, then configure dedicated read-only credentials and run one collection. Enable the collector timer only after actual metrics match Proxmox. No billing, payment, provisioner or customer VM deployment is needed.

Rollback: disable/stop only `cloud-portal-monitoring.timer` and `cloud-portal-monitoring.service`. Page then shows stale readings. Revert the dashboard change after preserving later unrelated code, recollect static assets and restart only Cloud Portal if removing the UI. Revoke only the dedicated monitoring tokens/user permissions when no longer needed. Do not remove backups, production VMs or existing workers.

## Validation boundaries

Automated tests cover owner/customer/staff isolation, separate session cookies, no infrastructure calls while viewing, rendering/escaping, unknown and stale states, backup selection/exclusion and timestamps, latest task failures, partial API errors, TLS enforcement and secret omission. Mocked API responses verify behavior, not live connectivity. Preview data is synthetic and visibly labeled; it is never seeded into production.

Live verification still needed: token scope and CA trust on both hosts, snapshot ownership, actual task/archive API response shape, automatic collection cadence, browser owner access after deployment and initial reading comparison. Record deployment commit, host, commands, outcomes and last collection only after these checks succeed.

## Overview and Graphs tabs — added 26 October 2026 (review work, not deployed)

The Monitoring page now has two tabs in the same document: **Overview** (the existing snapshot view, restyled with host cards, resource-health labels, compact storage table and a searchable VM/template inventory) and **Graphs**. Switching tabs never reloads the page or contacts Proxmox; the selected tab, host, time range and VM filters are remembered in the browser (`localStorage`, per viewer).

### Where history comes from

Graphs use Proxmox's own built-in RRD history, requested **on the web server** with the same read-only token the collector already uses. Verified against the Proxmox source: `GET /nodes/{node}/rrddata` needs `Sys.Audit` on the node and `GET /nodes/{node}/storage/{storage}/rrddata` needs `Datastore.Audit` on the storage, both included in `PVEAuditor`. No privilege change, migration, database table, time-series service or daemon is needed, and nothing is written to disk. The browser only talks to `/management/monitoring/history/` and never sees Proxmox URLs, tokens or raw responses. Results are cached in Django's cache (per web worker process) for 60 s (1 hour), 300 s (24 hours) and 900 s (7 days); a failing Proxmox is retried at most every 15 s and the last good history (up to 6 hours) is shown marked stale. At most one history load per host and range runs at a time, with a 10 s budget; storage requests are limited to eight names taken from the saved snapshot, never from the request.

Supported ranges: 1 hour, 24 hours, 7 days (Proxmox `hour`, `day`, `week`, AVERAGE). Sample spacing is Proxmox's own (about 1 min, 30 min and 3 h respectively).

### How values are interpreted

- CPU: Proxmox `cpu` is a 0–1 fraction of all cores, shown as percent. Memory: `memused / memtotal`. Storage: `used / total`, plus the root filesystem from the node RRD.
- Network: Proxmox `netin`/`netout` are bytes per second and are converted to bits per second. Per `pvestatd`, these are the **sum of the node's physical interfaces only**; bridges, bonds' virtual devices and VM interfaces are not added, so nothing is double-counted. There is no per-interface breakdown, and the chart says so.
- Missing samples are `null` and drawn as gaps, never zero; a real 0 is kept as 0. A filler timestamp is inserted after any hole wider than 1.5 sample steps so lines break across outages.
- "Current snapshot" is the last saved collection; "Last history sample" is the newest point on the chart. They are labelled separately because they can differ by a few minutes.
- Times display in `MONITORING_TIME_ZONE` (Asia/Manila, "PHT"); Django's `TIME_ZONE` and stored data are unchanged.

### Settings (all optional, defaults in `cloud_portal/settings.py`)

`MONITORING_THRESHOLDS` (percent warning/critical for cpu, memory, storage; defaults 85/95, 80/90, 80/90 — storage warning keeps the earlier 80%; invalid values fall back to defaults so alerts cannot be switched off by a typo), `MONITORING_HISTORY_CACHE_SECONDS`, `MONITORING_HISTORY_BUDGET_SECONDS`, `MONITORING_COLLECTION_INTERVAL_SECONDS` (display text only), `MONITORING_TIME_ZONE`, `MONITORING_TIME_ZONE_LABEL`. No new `.env` entries. Run `collectstatic` on deployment: new files are `monitoring-graphs.js` and `vendor/uplot/` (uPlot 1.6.32, MIT, byte-identical to the npm package, served locally).

### Known limits

- Refresh view reloads the saved snapshot and, on the Graphs tab, re-requests cached history. It never starts a collection. Automatic update is opt-in per viewer and pauses while the browser tab is hidden.
- Backup coverage remains "Not verified" when PVEAuditor hides archives; this release did not change that.
- Chart tooltips are pointer-driven. Keyboard and screen-reader users get tabs, host/range controls, a text summary on each chart (latest, highest) and per-series latest values in the legend.
- Storage names for the chart come from the last saved collection; a newly added storage appears after the next collection.
- Not yet verified against live Proxmox: field names and units were checked in Proxmox source, and behaviour with fixtures, but no live RRD response has been read. Verify once after deployment (open Graphs for each host and compare with the Proxmox node Summary).
