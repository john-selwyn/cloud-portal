# Customer accounts — prepared 20 October 2026

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
