# Infrastructure monitoring

Status: integrated with the new admin UI for review, 15 October 2026; no production deployment or live collector verification yet.

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
