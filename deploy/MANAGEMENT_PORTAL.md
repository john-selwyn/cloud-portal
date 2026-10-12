# Staff Management Portal

Development verified: 11 October 2026. **Deployment preparation updated: 12 October 2026.**

The internal rename prerequisite is now complete according to the user's live terminal evidence. VM200 connects to `cloud_portal_db` as `cloud_portal_user`, Django checks pass, one active staff superuser exists, and `cloud-portal.service` is active. The latest inspected live commit is `738156c` on `codex/windows-rdp`. Its subsequent documentation/environment-example commits have been merged into this feature branch so a fast-forward rollout preserves the live history. The Management Portal itself is not yet verified as deployed. No production migrations are needed for this feature.

The 11 October handoff below is historical. Its statements that the rename was unfinished and production still used `billing_db` are superseded by [the verified cutover record](CLOUD_PORTAL_RENAME.md) and the 12 October deployment preparation above.

## Branch and production boundary

- Repository: `john-selwyn/cloud-portal`.
- Feature branch: `feature/staff-management-portal`, based on `refactor/cloud-portal-internals` at `ecbfd6d34479107c3cd16fe0832433f813c05695`.
- This feature introduces no models, migration files, database rename, or production configuration changes. Its Django app is `portal` and project is `cloud_portal`.
- Latest user-verified live handoff: VM200 `10.50.0.22`, hostname `cloud-portal`, directory `/opt/cloud-portal`, unit `cloud-portal.service`, branch `codex/windows-rdp`, commit `21dcad5`. Production PostgreSQL remains `billing_db` with the original application tables.
- The internal rename was previously tested in `/opt/cloud-portal-rename-test` against `cloud_portal_rename_test_20261010`, with `portal_` tables and 146 tests passing. Those are handoff facts, not new live checks from this feature task.
- No live SSH, deployment, service restart, production migration, payment, or provisioning request was performed during this work.

## Using the portal

After a separately reviewed deployment, open `/management/` and sign in with an active staff account. Staff also see a Management link in the customer portal navigation. Signing in alone does not grant access to model records; assign only the necessary Django permissions.

| Area | Behavior | Permissions |
| --- | --- | --- |
| Customers | Search profiles by name, company, username or email; edit name, company and phone; account ownership is fixed | `view_customer`; `change_customer` for edits |
| VPS services | Search by customer, order number or VMID; filter status; paginate; open the order | `view_order` |
| Orders | Search, filter and inspect order/provisioning/access endpoint state | `view_order` |
| Reconciliation | Confirm a CSRF-protected POST to fetch and apply existing provisioner status | Both `view_order` and `change_order` |
| Plans | Search, create and edit plans; deactivate plans; reject negative prices and zero resources | `view_vpsplan`, plus `add_vpsplan` / `change_vpsplan` as needed |
| Invoices | Search and filter invoice records; inspect amounts, due dates and settlement state | `view_invoice` |
| Payments | Search by transaction or invoice number; filter provider/status; inspect payment evidence | `view_payment` |
| Subscriptions | Inspect active/cancelled/expired subscriptions and billing dates | `view_subscription` |

Django's standard change permission also grants viewing of that model's admin list/detail. Use the listed view permissions for consistent access to overview totals and services. No accounts, staff grants or groups are created automatically. A trusted superuser manages users/groups through the legacy `/admin/` interface. Ordinary staff are denied access to **all** legacy admin URLs, including direct POSTs, so old unrestricted model forms cannot bypass the Management Portal's workflow protections. Existing non-superuser admin operators must use `/management/` after deployment; review their permissions first.

The existing registration workflow creates customer accounts and their profiles. This portal edits those profiles; it does not invent a second account-creation or password workflow. Customer deletion and reassignment are disabled. Plan deletion is disabled; use `is_active` to retire a plan. Once a plan has orders, its name/CPU/RAM/storage become read-only here because unsent orders still use those resources at dispatch. Create a new plan for a resource change. Existing order amounts remain fixed when plan prices change.

## Business logic and safety

`portal/management_admin.py` reuses the existing model admin definitions and Django's permission, CSRF, forms, search, filtering, pagination and audit facilities. It exposes a separate named admin site, rather than duplicating the customer's checkout/payment code. `cloud_portal/urls.py` mounts the sites. The management templates live in `portal/templates/management/`; the staff navigation link is in `portal/templates/portal/base.html`.

- Orders, invoices, payments and subscriptions cannot be added, manually edited or deleted in Management, even by forging POSTs or granting their change/delete permissions.
- Payment raw responses, provisioning payloads/leases and SSH key material are omitted from this surface. It does not reveal Windows passwords.
- Reconciliation calls `portal.provisioning.get_vps_provisioning_status`. Existing verified-payment, lease, polling and identity checks remain authoritative. The only remote operation is the existing status GET; the workflow can update local order state and create/reuse an activation subscription.
- Merely viewing/searching pages performs no provisioner HTTP calls. There are no staff payment-success shortcuts, manual invoice settlement, new provisioning requests, retry buttons, power actions, refunds, suspension or deletion actions.
- Customer/plan changes and accepted reconciliation calls use Django's admin log with the acting user. Failed validation displays an error without claiming completion. This is an operational audit record, not an immutable compliance ledger.
- `/admin/` preserves existing unrestricted tools for trusted active staff superusers only. A superuser retains their existing authority; Management is not a security boundary against superusers.

## Verification performed

Environment: local Windows development checkout, Python 3.12 and Django 6.1.1, existing local dependency directory `../billing/.test-deps`, disposable SQLite test database. Integrations were mocked for tests. No production `.env` was copied.

Run from **Windows PowerShell in the feature checkout**; no administrator rights required:

```powershell
$env:PYTHONPATH = (Resolve-Path ../billing/.test-deps).Path
$env:DEBUG = 'True'
$env:SECRET_KEY = 'local-management-tests-only'
python manage.py test --noinput
python manage.py makemigrations --check --dry-run
git diff --check
```

The `PYTHONPATH` line is specific to this workstation's existing test dependencies. In another development environment, use its isolated interpreter with the repository requirements installed. The displayed secret is an explicitly non-production test value.

- `python manage.py test --noinput`: **168 tests passed**, comprising the existing 146 and 22 Management tests. The test runner creates/removes its isolated test database; it is not a production migration command.
- System checks: **no issues**.
- `makemigrations --check --dry-run`: **No changes detected**; no schema files generated or production tables changed.
- `git diff --check`: **clean**.
- Browser review on `127.0.0.1:8765` with synthetic records: staff sign-in, overview, VPS search, read-only order detail and reconciliation confirmation rendered successfully. The preview database was separate from both the production database and the user's rename test database.

Coverage includes anonymous/customer/inactive-staff denial, missing model permissions, legacy-admin bypass attempts, superuser legacy access, forged workflow edits, CSRF, method restrictions, sensitive-field omission, customer ownership protection, plan validation/resource preservation, pagination, permission-filtered totals, audit attribution, unpaid-order refusal, and a successful reconciliation with mocked provisioner GET that reuses a single subscription.

### Additional PostgreSQL verification — 11 October 2026

The user requested direct testing. The same feature code at `630f19c` was tested again on SQLite (**168 passed in 18.682 seconds**) and on an isolated local PostgreSQL instance (**168 passed in 40.457 seconds**). No application-code repair was necessary.

- PostgreSQL identity queried over the actual connection: **PostgreSQL 17.11, x86_64-windows**, listening only on `127.0.0.1:55432`.
- Portable binaries came from [EDB's PostgreSQL binary downloads](https://www.enterprisedb.com/download-postgresql-binaries?lang=en), archive `postgresql-17.11-3-windows-x64-binaries.zip`. No Windows service was installed.
- A new disposable cluster used SCRAM password authentication and a random temporary credential. No production configuration or credentials were used. The initialization password file was removed after cluster creation; no credential is recorded here.
- Local base database: `management_portal_validation`; disposable Django test database: `test_management_portal_validation`. These are unrelated to the server-side rename-test database.
- Applying the existing migrations to this empty local database succeeded. Schema introspection verified `portal_customer`, `portal_invoice`, `portal_order`, `portal_payment`, `portal_subscription`, `portal_vpsplan`, `portal_vpspoweroperation`, and `portal_xenditcheckout`, with no `billing_` application tables.
- Django system checks passed and `makemigrations --check --dry-run` again reported no changes.
- The runner destroyed its test database and stopped the temporary PostgreSQL server successfully at completion. The downloaded runtime remains only as local workspace test tooling.

The exact verified workstation command, from **Windows PowerShell in the project workspace root**, was:

```powershell
python -u management_pg_test.py
```

`management_pg_test.py` is a workstation-local helper outside this Git repository. It creates a fresh cluster under `.management-pg-check`, binds only to localhost, overrides Django's database target before initialization, clears integration credentials, runs migrations/checks/tests, and stops the cluster in a `finally` block. It requires the extracted portable runtime in `.management-pg-check/runtime/pgsql` and the existing local Python test dependencies. This command is **LOCAL TEST CONFIGURATION**, not a server deployment procedure. It was executed with permission to run localhost processes outside the restricted shell sandbox, not as a PostgreSQL Windows service.

This confirms PostgreSQL behavior on a clean renamed schema. It does not test a production-data rename, Ubuntu service configuration, Nginx, or actual payment/provisioner endpoints; those endpoints remain mocked in the automated suite.

## Remaining verification and rollback

This is development verification on SQLite and PostgreSQL, not production or server-staging verification. After the rename plan is completed/reviewed, validate the branch in a separate server staging checkout with representative non-sensitive data and reviewed staff roles. Do not use production credentials or enable real payment/provisioning integrations for a casual preview. Review UI usability with the intended staff before promotion.

No rollback is required on production because nothing was deployed. To abandon the feature before deployment, leave its branch and use the existing rename branch; no feature schema rollback is needed. Future deployment rollback must use a revision compatible with the completed rename schema, preserve any profile/plan edits, and follow the separately approved rename recovery procedure. Do not deploy the old pre-rename app against renamed tables.
