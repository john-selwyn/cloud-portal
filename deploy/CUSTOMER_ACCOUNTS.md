# Customer accounts — prepared 20 October 2026

## Latest verified state — 20 October 2026

This section supersedes earlier restore/preflight/apply-pending statements below. On VM200, the standalone review checkout at `f1605c85f24c32eaa27dacd6c1871491e616f7a4` successfully ran `deploy/rehearse_accounts.py --env /opt/cloud-portal/.env --database cloud_portal_accounts_rehearsal_20261020 --apply`. The helper verified the isolated PostgreSQL 18.6 database, disabled integrations, applied `portal.0012_customer_accounts... OK`, and confirmed all original records unchanged against the retained private baseline: 6 users/customers, 2 admin log records, 13 sessions, 2 plans, 29 orders/invoices, 26 payments/checkouts, 20 subscriptions and 19 power operations. Original group/grant association tables remained empty. Existing customer verification requirements stayed false, new account tables stayed empty, Django checks found no issues, and the helper printed `REHEARSAL PASSED`. Production was not migrated or restarted by this command. Keep the test database, staged dump, NAS backup and private baseline; do not recreate the baseline after migration.

The initial connection was rejected because PostgreSQL access rules omitted the accounts rehearsal database. VM300 SSL was verified on. The original `/etc/postgresql/18/main/pg_hba.conf` was backed up to `pg_hba.conf.before-accounts-20261020`, then an exact `hostssl cloud_portal_accounts_rehearsal_20261020 cloud_portal_user 10.50.0.22/32 scram-sha-256` rule was added and parsed without errors at line 145. A reload was instructed; no reload output was supplied, but successful preflight/apply establishes working runtime access. Later cleanup should remove only that temporary rule, validate and reload; cleanup has not run.

Production checkout was subsequently reported at `289825f93df7d9851def505dd91f57a746331a52` with Nginx active. The current account review incorporates that revision's invoice listing and shared client shell, retaining account navigation and using a new shared-stylesheet cache version. Running Django process identity is not established by checkout/Nginx output. Phone visual acceptance and production rollout remain pending; email-provider configuration stays owner-deferred.

User-supplied VM200 diagnostics verified `/etc/nginx/sites-enabled/cloud-portal` proxies to `http://127.0.0.1:8001` and overwrites `X-Real-IP` with `$remote_addr`. Gunicorn listens only on `127.0.0.1:8001`. Current deployed code reports no `CUSTOMER_TRUSTED_PROXY_IPS` setting. The proposed account-release private environment setting is `CUSTOMER_TRUSTED_PROXY_IPS=127.0.0.1`; it has not been configured or verified live. Verify separate real client buckets after rollout. The observed Nginx listener is HTTP port 80; HTTPS/canonical public origin and real mail require separate verification before email delivery is enabled.

## Current review and rehearsal state — 20 October 2026

This section supersedes the older monitoring-only baseline and publication status below. User terminal output now verifies production `/opt/cloud-portal` on `codex/windows-rdp` at `a1a17752159fe9fe9c912c0687c88de3607c3996`, hostname `cloud-portal`, portal migrations 0001–0011 applied. Only untracked `billing/` and `monitoring-ca/` were reported; neither was changed. The account review now includes that current source, retaining the completed Dashboard, My VPS, Orders and Management changes. The shared stylesheet-version conflict was resolved while retaining the current navigation/template blocks.

Review also fixed whitespace variants bypassing an identifier's login-rate bucket. Regression coverage verifies differently padded identifiers share their limit across different client IPs. **277 combined application tests passed on isolated PostgreSQL 17.11** after source reconciliation. The guarded helper's separate PostgreSQL 17.11 integration checks passed: production-name refusal, two-stage preflight, peer-client refusal, preserving migration and repeat, original credential/financial tamper detection, and refusal of unrelated renewal history. Test clusters stopped. These remain local tests, not the restored-production rehearsal.

User-executed VM300 evidence: `ictdatabase`, NAS `10.50.4.210:/volume1/PostgreSQLBackup` mounted on `/mnt/postgresql-backup`; fresh existing backup job completed with directory `/mnt/postgresql-backup/native/2026-10-20_01-58-00`. The portal dump was restored into a new `cloud_portal_accounts_rehearsal_20261020`, owner `cloud_portal_user`, with PUBLIC CONNECT revoked. Restore used `--exit-on-error --single-transaction`, no `--create` or `--clean`, and a private postgres-owned mode-600 staged dump. Verified restored server: PostgreSQL 18.6. Verified counts: 29 invoices, 26 payments, 20 subscriptions; portal migrations 0001–0011 present. Production was not the restore target. Retain the source NAS dump, staged copy and test database until rehearsal/cleanup decisions are verified separately.

### Guarded accounts rehearsal

Use only a new standalone review checkout under the VM200 user's home, separate from `/opt/cloud-portal`. `deploy/rehearse_accounts.py` reads `/opt/cloud-portal/.env` privately, refuses the configured live database and non-accounts-rehearsal names, verifies actual database identity, rejects unrelated migration plans/peer clients, and disables mail/payment/provisioning/monitoring integrations. Only portal `0012_customer_accounts` is allowed. First run is database-read-only and saves original-column counts/fingerprints for users, credential hashes, grants, sessions, admin history and all operational/financial tables in a private mode-600 baseline. No row values are displayed or saved. The apply stage requires that retained baseline and checks preservation again before and after migration. Existing customers must not acquire a verification requirement; new account tables must remain empty.

From that isolated checkout, on **VM200 Ubuntu** (proposed until verified there):

```bash
/opt/cloud-portal/venv/bin/python deploy/rehearse_accounts.py --env /opt/cloud-portal/.env --database cloud_portal_accounts_rehearsal_20261020
```

Expected: exact test database identity, original counts, one pending account migration and `PREFLIGHT PASSED`. Stop and inspect this result before running the separate apply step:

```bash
/opt/cloud-portal/venv/bin/python deploy/rehearse_accounts.py --env /opt/cloud-portal/.env --database cloud_portal_accounts_rehearsal_20261020 --apply
```

Expected: `0012_customer_accounts... OK`, original records unchanged, empty account tables, then `REHEARSAL PASSED`. This changes only the named restored copy. Never connect the production web service or workers to it. Do not copy `.env` into the checkout, start a preview against the restored customer data, create a baseline after migration, overwrite a failed baseline, or reuse the separate renewal rehearsal database. No production restart or migration belongs to this helper's workflow. A later failure can occur after the test schema changed; preserve evidence and fix forward in that test copy instead of concealing it by recapturing a baseline.

Current milestone: fresh restore verified; isolated VM200 preflight/apply still pending. Phone visual review, verified Nginx client addressing and a reviewed production rollout remain later checks. Real email configuration remains deferred.

Status: implemented and tested locally; not deployed. Customer email delivery is intentionally deferred by the owner. No production accounts, credentials, services or financial records were changed.

## Source and scope

Branch `feature/customer-accounts`, based on the deployed monitoring implementation. All 115 baseline files were compared with GitHub `5bbfaea323019f1394330e4cb6fbb83591f9b9a1`, allowing only CRLF/LF differences. Local history uses equivalent baseline commit `7078dc9`; do not confuse that SHA with a production deployment. The separate renewal checkout and its existing uncommitted work were preserved.

- Profile: name/company/phone with appropriate autofill; security and current/pending email status on Account. Username remains stable.
- Registration: normalized email, duplicate-address checks including staff addresses, optional company/phone, password validation, automatic customer profile, welcome message and account review. Caller-supplied staff flags/ownership are ignored.
- Login: username or uniquely matching email. Historical duplicate emails cannot authenticate by email; username still works. Staff accounts remain excluded.
- Password change: current password required; Django preserves this browser session and invalidates other sessions.
- Password recovery: matching active customer only, generic result for unknown/ambiguous/staff/inactive addresses, canonical HTTPS origin, one-hour Django token, no automatic login, replay/expiry/role checks. Confirmation rechecks the token under a user row lock.
- Email change: current password required, current address remains until confirmation. Signed one-hour link; GET previews, CSRF-protected POST confirms. Resending/replacing/cancelling invalidates the previous pending request; password or external email changes invalidate it too. Addresses are reserved with a database unique constraint across customer requests.
- Optional email verification gate: applied only to new registrations when explicitly enabled. Existing customers are not marked verified and do not lose access. New gated customers can sign in, edit their profile/email/password, and request verification, but cannot use protected services until confirmed.

## Safe disabled-mail behavior

Keep these in the private VM200 `/opt/cloud-portal/.env` until real delivery is verified:

```dotenv
CUSTOMER_EMAIL_ENABLED=False
CUSTOMER_REQUIRE_EMAIL_VERIFICATION=False
```

Defaults use a dummy mail backend, not console logging. Profile, registration, username/email sign-in and authenticated password changes work. Email-dependent pages explain that setup is pending; no confirmation/reset email is sent. Do not enable required verification without working mail: Django checks reject this configuration. Turning the global requirement off later affects future registrations only; it does not remove a requirement already attached to a newly registered customer.

When the owner resumes mail setup, configure `CUSTOMER_PUBLIC_ORIGIN` as the actual HTTPS origin (no path/query/fragment/credentials), `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`. Choose exactly one of STARTTLS (`EMAIL_USE_TLS=True`, typically 587) or implicit TLS (`EMAIL_USE_SSL=True`, typically 465), according to the provider. Certificate verification remains enabled. Verify provider/domain delivery and spam handling using an owner-controlled test inbox before enabling email or the new-registration gate. Store secrets privately, never in Git/GitBook/chat. No provider or live hostname is assumed here.

## Request limits and Nginx prerequisite

Counters live in PostgreSQL, shared across web workers; keys are keyed hashes, not raw email/IP values. Counts use fixed windows; successful requests count too.

| Action | Per identity | Per source IP |
|---|---|---|
| Login | 30 / 15 minutes | 300 / 15 minutes |
| Password change | 10 / 15 minutes | 100 / 15 minutes |
| Recovery, email change, resend (separate buckets) | 5 / hour | 50 / hour |
| Registration | none | 10 / hour |

Before rollout, verify how Nginx connects to Gunicorn and what `REMOTE_ADDR` actually contains. By default forwarded headers are ignored. If Nginx is the source, it must overwrite `X-Real-IP` with `$remote_addr`, direct untrusted Gunicorn access must be blocked, and only the exact verified proxy source IP(s) may be listed in `CUSTOMER_TRUSTED_PROXY_IPS`. Do not copy guessed addresses or trust arbitrary `X-Forwarded-For`. A missing/wrong proxy configuration can make multiple customers share an IP bucket; deliberate attempts against an identity can impose a temporary lock. Verify separate client buckets before public rollout. No Nginx file/interface was inspected or changed in this implementation.

Optional maintenance after rollout, as the portal service user in `/opt/cloud-portal`:

```bash
./venv/bin/python manage.py cleanup_account_requests
```

CONFIGURATION/DATA CHANGE: deletes only expired hashed counters and expired unconfirmed email requests; retains accounts, verified addresses and all financial records. Locally tested. No timer was installed. Expired pending reservations can also be reclaimed by a new request. No tokens, passwords or SMTP exception details are printed by the account mail handlers.

## Migration and rollout

Migration `0012_customer_accounts` adds two account-support tables and a default-false field on Customer. It does not rewrite existing emails/passwords, move ownership, create financial records, or alter invoices/payments/subscription dates. It still changes the production schema and may briefly acquire database locks: take a fresh verified backup and rehearse on an isolated restored database first.

This branch deliberately excludes the pending renewal migration. If combined with `feature/renewal-invoices`, there will be two migrations descending from portal 0011. Prepare and test a merge migration with both dependencies before combining/deploying; do not rename applied migrations, fake them, or deploy an older financial schema over renewal rows.

First production step, READ-ONLY, on **VM200 Linux shell**, as the repository owner:

```bash
cd /opt/cloud-portal
git status --short
git branch --show-current
git rev-parse HEAD
```

Expected: identify current revision, local changes and whether renewals were deployed since the last verified monitoring revision. Stop for any unexpected source/schema drift. These commands are proposed for this milestone, not newly verified on production.

After source review, backup/rehearsal, verified proxy identity and an approved rollout window, use the reviewed account commit and inspect:

```bash
./venv/bin/python manage.py check
./venv/bin/python manage.py migrate --plan
```

Expected: only the reviewed account migration on the matching 0011 production base. Preserve `.env` and take a rollback source reference. Applying the migration, collecting static files and restarting `cloud-portal.service` remain future deployment actions; a portal restart may briefly interrupt requests. Do not blindly pull a feature branch into a drifting live checkout.

Production acceptance: old customer login/profile/services; new registration; password change/current versus other browser sessions; customer/staff cookie separation; denied staff recovery; two independent clients' request counters. With mail still off, confirm honest unavailable messages and no mail. Later, separately verify delivered emails, canonical HTTPS links, GET versus POST confirmation, expiry/replay, old/new addresses, and password recovery in an owner-controlled account.

## Verification actually completed

- Full application suite: **239 tests passed** on a disposable PostgreSQL **17.11**, bound to `127.0.0.1:55435`, integrations disabled and synthetic fixtures only.
- After final proxy and shared-counter corrections: **31 targeted account/migration tests passed** on a fresh disposable PostgreSQL 17.11. Includes two workers racing for one email, parallel counter updates, trusted/untrusted/malformed proxy headers, and schema migration from 0011 preserving all original representative customer/order/invoice/payment/subscription fields. Both test clusters stopped; no Windows service installed.
- Existing JavaScript provisioning suite: **9 passed**. Django system and migration-consistency checks passed. No production PostgreSQL 18.6/restored-data rehearsal is claimed.
- Focused SQLite tests were used during development; early failures exposed admin-template precedence and an unbound throttled-form error. Fixed with explicitly named `customer_auth/` templates and a dedicated throttled-login message; subsequent PostgreSQL coverage passed.
- Desktop browser review uses a synthetic, temporary localhost preview and in-memory mail. Account and email-change layouts inspected; automated flow tests cover the other routes. A 390px iframe review was attempted but the app browser did not render the frame; phone visual acceptance is still pending. The preview uses a same-origin-only frame setting in its standalone helper; production frame policy is unchanged.

## Recovery and remaining limits

Prefer a forward correction and keep the additive account tables. Reversing this migration discards verification/reservation/rate-limit state and is not a routine rollback. Reverting to the old app also stops enforcing newly required verification; review that consequence before an emergency code rollback. Existing financial records are outside this migration's scope. Do not reset passwords or delete users to repair an email problem.

Legacy administrative User edits bypass these public customer workflows. Investigate historical duplicate addresses and stale reservations privately; never bulk-normalize or reassign them without verified ownership. Generic recovery pages reduce account disclosure but synchronous SMTP timing is not an enumeration-proof queue. These application limits complement, not replace, edge protections and operational monitoring.

Remaining: source publication/review, isolated restored-production migration rehearsal, live proxy validation and rollout acceptance, phone visual review, and the owner-deferred email configuration/end-to-end delivery. No live rollout, provider configuration or customer message occurred here.

## Publication follow-up — 20 October 2026

The owner explicitly approved public publication after reviewing the local result. [Draft PR #7](https://github.com/john-selwyn/cloud-portal/pull/7) publishes the implementation on `feature/customer-accounts`, based on `feature/monitoring-admin-ui` at `5bbfaea323019f1394330e4cb6fbb83591f9b9a1`. Published implementation commit: `eb29bd9b726677aa35a7c5a4d2c36cefc531d65d`; equivalent local implementation commit: `50e3f77`. All 33 uploaded file blobs were checked against the locally committed content with no mismatches. The GitHub comparison contains one implementation commit, 33 changed files, 1172 additions and 25 deletions.

Source publication is now complete; the publication-pending item above is superseded. The PR remains draft and unmerged. Review, restored-data rehearsal, live proxy validation, phone acceptance, deployment and email configuration remain pending. This follow-up changes documentation only; the prior application tests are not new production verification.
