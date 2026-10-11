# GitBook update draft — 11 October 2026

**Publication status: NOT SAVED TO GITBOOK.** Read access succeeded. Creating a change request through both the generic operation and curated tool failed with HTTP 403: "This method cannot be accessed with this authentication (requires user auth)." No pages were changed. Restore suitable GitBook write authentication before publishing this draft.

## Current System Status — affected rows only

Preserve unrelated infrastructure observations and their original dates. The following handoff supersedes the October 9 billing names and old repository references for VM200; it does not freshly verify the other components.

| Component | Latest state | Evidence / limitation |
| --- | --- | --- |
| VM200 Cloud Portal | `10.50.0.22`, hostname `cloud-portal`, `/opt/cloud-portal`, `cloud-portal.service`; last verified live branch `codex/windows-rdp`, commit `21dcad5` | Latest user-provided verified rename handoff; no live inspection in this task |
| Repository | `john-selwyn/cloud-portal`; internal rename branch `refactor/cloud-portal-internals`, commit `ecbfd6d34479107c3cd16fe0832433f813c05695` | Branch hashes read from GitHub in this task; rename is NOT deployed |
| Production PostgreSQL | `billing_db`, original application tables | Latest verified user handoff; do not apply renamed app migrations to production |
| Rename test | `/opt/cloud-portal-rename-test`; DB `cloud_portal_rename_test_20261010`, renamed `portal_` tables; 146 tests passed | Prior verification reported in handoff; not rerun on that server here |
| Staff Management Portal | `feature/staff-management-portal` based on `ecbfd6d`; `/management/`; customers, VPS services, orders, plans, invoices, payments, subscriptions | Locally verified: 168 tests pass; no new schema changes; browser reviewed with synthetic data; not deployed |
| Active blocker | Production internal rename/cutover unfinished; GitBook writes unavailable | Keep Management development separate from cutover; restore GitBook write authentication |
| Next action | Review Management changes against the rename branch; complete/review rename separately, then validate Management on isolated PostgreSQL staging | No deployment or production migrations authorized in this task |

## New page: Staff Management Portal

Use `deploy/MANAGEMENT_PORTAL.md` from the feature branch as the source for the new operational page. It records scope, permission matrix, protected workflow actions, changed legacy-admin access, source files, exact local verification commands/results, remaining PostgreSQL verification and rollback limits.

## Architectural decision / Development Changelog

11 October 2026 — Developed a dedicated staff Management Portal using a separate Django AdminSite and the existing model admins/business logic. Active staff plus model permissions are enforced server-side. Existing customer ownership, checkout, payment verification and provisioning logic remain authoritative. Financial/service lifecycle records are inspect-only; explicit confirmed reconciliation invokes the existing payment-checked GET workflow. The unrestricted legacy admin is reserved for active staff superusers to prevent ordinary staff bypass. No new schema or deployment configuration is introduced.

Validation: 168 local SQLite tests pass, including 22 added security/management tests; Django checks pass; no model migration changes detected; browser smoke check uses synthetic data. PostgreSQL staging and production remain unverified by this task. The earlier internal rename and its pending production cutover are separate work.

## Pages consulted

- Current System Status (read first).
- VPS billing and provisioning.
- AI Assistant Operating Guide.
- Development and production safety.

GitBook search results for "cloud portal" were also inspected; they did not document the newer rename handoff. Source priority: user-designated latest verified handoff for rename state; current GitHub branch hashes and local test output for feature development. No claim of a live infrastructure verification or successful GitBook write is made.
