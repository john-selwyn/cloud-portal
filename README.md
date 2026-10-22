# Visual consistency preview — evidence

Companion to the draft pull request for `design/visual-consistency-preview` (target `feature/customer-accounts`).
This branch holds screenshots and notes only. It is **not** part of the pull request and must not be merged.

- Baseline (VM200 production, per user-supplied output): `e44d4f0543adc3522edb12e3a4df2a8aad48a4c8`
- Cleanup commits: `07208bc` then `5147723351b2672ec5c81fa4d7d1ba6a3d9828f2` (final)
- Scope: presentation only (`.html` and `.css`); 9 files; no Python, settings, models, migrations, forms, URLs or JavaScript changed.
- Screenshots use placeholder data in a throwaway database. Desktop 1440px, phone 390px. `screenshots/before/` is the baseline, `screenshots/after/` is `5147723`.

## Test results (accurate)

| Check | Result |
|---|---|
| `manage.py test portal` | **309 ran: 307 passed, 2 skipped** |
| Skipped | 2 PostgreSQL-only row-lock concurrency tests (`CustomerAccountConcurrencyTests`): "Row-lock concurrency requires PostgreSQL" |
| Database backend | Django's temporary **in-memory SQLite** test database (`file:memorydb_default?mode=memory`). Not PostgreSQL, not production, not VM300 |
| `manage.py check` | no issues |
| `makemigrations --check --dry-run` | no changes detected |
| `node --test portal/test_provisioning_poll.cjs` | 9 of 9 passed |

The 2 skipped tests were **not run anywhere**; PostgreSQL concurrency behaviour is unverified by this change (it does not touch that code).

## Regression check on pages this change does not target

Baseline vs `5147723`, pixel-diffed in headless Chromium at 1440px and 390px: VPS detail (active and provisioning), order detail (active and pending), provisioning status, invoice, plan checkout, payment return and cancel, password change, email change, password reset, and six staff Management pages.

- Desktop: all pages identical (0.00% pixels differ).
- Staff pages: identical on desktop and phone (they do not use the shared customer stylesheet).
- Customer/public pages on phone: differences only in the header (new mobile navigation); nothing differs below the header, apart from one animated status dot captured at a different frame.

## Not verified

- Real devices and browsers other than headless Chromium; screen readers.
- Live payment (Xendit), provisioning and power actions (not exercised).
- Anything in VM200's untracked `billing/` and `monitoring-ca/` directories (not visible from here).
- Browsers without CSS subgrid fall back to a padded gap above prices (previous behaviour).

Deployment and rollback: see `DEPLOYMENT_VM200.md`.
