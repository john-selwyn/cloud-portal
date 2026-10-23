# VM200 runbook review — 23 October 2026

Status: documentation review only. No production merge, checkout, deployment,
database migration, service restart or rollback was performed.

## Release blocker

Latest verified production source is
`7fa0023af434929b27d243e73a9a3a11ef8b0dd6`, with portal migration 0013 and
Ubuntu Server ordering enabled. This comes from the owner's VM200 output and
GitBook Current System Status, consulted during this review.

PR #9 remains at `5147723351b2672ec5c81fa4d7d1ba6a3d9828f2`, based on
`e44d4f0543adc3522edb12e3a4df2a8aad48a4c8`. It is not a descendant of current
production. The runbook now pins the current baseline and rejects this target
before creating a static backup or rollback branch. A separately reviewed
target preserving the Ubuntu Server release is needed before deployment can
become executable. No application branch was rebased, merged or changed here.

The actual reviewed diff is **4 CSS files and 5 HTML files**, not the reversed
counts in the request. The runbook enforces both counts, exact paths and statuses:

- Added CSS: `portal/static/portal/customer-pages.css`.
- Modified CSS: `dashboard.css`, `portal-modern.css`, `storefront.css` in the same directory.
- Modified templates: `base.html`, `dashboard.html`, `my_vps.html`, `orders.html`,
  `plans.html` under `portal/templates/portal/`.

## Corrections

- Each block uses a subshell. Isolated commands use `env -i`, an empty disposable
  `.env`, and `PYTHON_DOTENV_DISABLED=1`; test DEBUG/SECRET_KEY cannot reach later
  production commands. Assertions verify SQLite engine/vendor, a database path
  resolving inside the disposable checkout, no network DB connection settings or
  additional database aliases, an in-memory test database, disabled email/test
  payments, and empty payment/provisioning/Hestia integration settings.
- Production blocks reject inherited database, integration, Django and Python
  control variables, including PGOPTIONS, DATABASE_URL, the Server ordering flag
  and PYTHONOPTIMIZE. The migration-plan check is read-only and asserts the
  PostgreSQL database identity; it never executes a migration.
- Exact release, branch, tree, scope and fresh tracked/untracked-state checks
  precede application mutation. Failed checks, collectstatic and CSS comparisons
  stop the block. CSS is checked again immediately before restart. HTTP transport
  failures cannot be hidden by a negated pipeline or a pipe ending in grep -q.
- A timestamped, private records directory has an overwrite guard. A named Git
  branch preserves the rollback commit. Static backup validation checks its
  exact checksum member, digest, readable archive, safe member paths/types,
  required stylesheets and recorded file count before rollback can reset files.
- Rollback requires the exact deployed SHA, expected branch, fresh tracked
  cleanliness, preserved rollback ref, unchanged billing/monitoring-ca metadata
  and a valid backup. Restored static files are compared against that backup.
- `billing/` and `monitoring-ca/` remain the only allowed untracked directories;
  only their path/type/size/mtime/mode metadata is inspected. No contents are read
  by the preservation checks. No git clean/stash or recursive production deletion
  is introduced. Disposable verification checkouts and rollback refs are retained.
- Deployment/rollback explicitly use umask 022 for web-readable static assets;
  records creation uses umask 077. Evidence stays on the evidence branch.

## Local verification

The shell blocks were extracted from the Markdown and checked with Bash. Local
fixtures use Git Bash on Windows, real Git repositories, real Django checks,
the reviewed branch's SQLite tests, real collectstatic and real tar backup/restore.
Git Bash synthesizes NTFS permission bits from the current umask: fixture-only
find/tar wrappers normalize that reporting so Linux preservation guards remain
unchanged in the published runbook.

Systemd, sudo, journal and HTTP are mocked. The production PostgreSQL read-only
plan response is mocked. Those boundaries, real Linux filesystem permissions,
VM200's actual static directory and real public HTTP behaviour are not verified
by these local tests.

The positive A–F fixture intentionally uses the historical `e44d4f0` baseline
with reviewed target `5147723` to exercise the proposed flow. It is not a claim
that this pair may be deployed now. A separate fixture uses the actual pinned
`7fa0023` / `5147723` pair and must abort before backup/ref/application changes.

The isolated reviewed-snapshot suite ran **309 tests: 307 passed, 2 skipped**
(PostgreSQL-only concurrency). It ran against an in-memory SQLite test database,
not production or PostgreSQL. Hostile parent DB/integration/test-payment/Server
flag variables were supplied to the isolated block and did not reach Django.

**All 29 local runbook checks passed**, including shell syntax, the full
historical-snapshot A–F rehearsal, and these rejection cases:

- Wrong baseline, remote target, reviewed tree, branch or rollback ref.
- Dirty tracked files, unexpected untracked files, changed billing metadata,
  and a failed Git status command.
- Missing/corrupt backup or wrong recorded backup count.
- Inherited DEBUG, DATABASE_URL, Server flag or Python optimization.
- Failed Django check, non-empty migration plan, failed collectstatic or CSS
  mismatch. A CSS change between deployment and restart also blocks restart.
- Rollback with a dirty tree, missing backup or unexpected HEAD; each stopped
  before `git reset`. HTTP failure prevents a success marker both after restart
  and during rollback verification.
- The actual current-baseline/reviewed-target pair aborts before any backup,
  rollback ref or application change.

Failures after a local fixture's fast-forward (for example failed collectstatic)
can leave that fixture's code/static files changed. The verified property is
that no later action/restart or success marker occurs; the runbook describes
guarded rollback and does not claim that every failure is mutation-free.

## Remaining work

Prepare and review a visual target retaining the current production baseline;
re-pin its SHA/tree/scope/test count, then obtain deployment authorization.
Live VM200/HTTP checks and actual deployment remain outside this review.
