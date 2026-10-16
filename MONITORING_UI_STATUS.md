# Monitoring in the Management UI

Prepared 15 October 2026. Not deployed or connected to live infrastructure.

Base: design/management-refinement at b579ebdc8199938a9ec3f6d9ae77d5b89809a3eb. Keeps the existing admin shell, separate staff sessions, sidebar, overview, services and record styling.

Adds owner-only Monitoring navigation and an overview shortcut; host resources, storage capacity, VM and template inventory, backup selection/archive coverage, recent backup tasks and review items. Read-only collector saves snapshots atomically; browser reads saved data only. Credentials are never stored in snapshots. TLS verification is mandatory. Stale/partial/missing readings are explicit. No notifications or IP/network changes. No migration or dependency changes.

Verification: full Django suite 211 passed and existing JavaScript suite 9 passed on the integrated Batch 1 layout; after preserving the latest Batch 2 stylesheet/services updates, all 19 monitoring tests passed again. No migration changes. Desktop (1440px) and phone (390px) rendered in the in-app browser; no horizontal page overflow at 390px. Filtering 1026 shows only that VM. Sample and empty snapshot states checked. Local preview uses clearly labelled synthetic data and no production connections.

Next: review the UI in the existing admin preview; configure dedicated read-only Proxmox tokens and trusted CA, run collector once and verify actual readings, then enable the provided timer. See deploy/MONITORING.md for setup, checks and rollback. Application services, native database dumps, website availability, certificate expiry and resource history remain outside this first version.
