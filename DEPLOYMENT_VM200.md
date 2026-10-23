# VM200 deployment and rollback — visual consistency preview (rev 2)

**Status: PREPARED ONLY. Nothing has been merged, deployed, migrated or restarted.** Run these steps only after explicit approval, one block at a time, and **stop at the first `ABORT`**.

This file lives on the `evidence/visual-consistency-preview` branch. It is not part of application PR #9 (`design/visual-consistency-preview`) and must never be added to it.

| | |
|---|---|
| Baseline (deployed, per VM200 output) | `e44d4f0543adc3522edb12e3a4df2a8aad48a4c8`, local branch `codex/windows-rdp` |
| Target | `5147723351b2672ec5c81fa4d7d1ba6a3d9828f2` (PR #9 head) |
| Target tree | `69e6ec4ca740de904c1a5d051aca8e615924453e` — a merged commit is acceptable **only if its tree is identical** |
| Scope | **9 files, presentation only: 4 stylesheets + 5 templates** (`git diff --name-status` shows 1 added + 3 modified CSS, 5 modified HTML; the reviewer's note of "five CSS and four HTML" does not match the diff, so the original counts are kept and enforced). CSS: `customer-pages.css` (new), `dashboard.css`, `portal-modern.css`, `storefront.css`. HTML: `base.html`, `dashboard.html`, `my_vps.html`, `orders.html`, `plans.html` (all under `portal/`). The blocks below enforce 4 CSS + 5 HTML + 0 other files. |
| Not changed | Python, settings, models, migrations, forms, URLs, JavaScript, `.env`, database. **No migrations.** |

Facts from the repository's `deploy/CLOUD_PORTAL_RENAME.md` (12 Oct) and `deploy/CUSTOMER_ACCOUNTS.md` (20 Oct): VM200 `/opt/cloud-portal`, user `ict-tech`, `cloud-portal.service` (Gunicorn, `127.0.0.1:8001`), Nginx site `cloud-portal`, assets in `/opt/cloud-portal/staticfiles`, public URL `https://proxmoxportal.dyndns.org`. Confirm each on VM200 first (block B checks the service and branch).

## How the blocks are built (read once)

- **Every block is a `( … )` subshell with `set -Eeuo pipefail`.** Variables, `cd`, `DEBUG` and `SECRET_KEY` cannot leak into your login shell or into later production commands. Block C's test settings exist only inside its own `env -i` child process.
- **Fail closed:** any failed guard calls `die` (prints `ABORT: …`, exits 1). Blocks D–F also print `STOPPED` on any non-zero exit. A block only writes its marker file (`$BK/state/*.ok`) when every step passed, and the next block refuses to start without the previous marker.
- **Production blocks refuse to run if the shell has inherited settings variables** (`DEBUG`, `SECRET_KEY`, `DB_*`, `XENDIT_*`, `PROVISIONING_*`, …). `settings.py` calls `load_dotenv()` without `override`, so an inherited variable would silently beat `/opt/cloud-portal/.env`. Open a fresh shell if a block reports one.
- **No `umask 077` in deploy/rollback blocks**, so collected static files keep the permissions Nginx needs.
- Blocks never run `git clean`, `git stash`, `git add`, `git checkout -- .` or `rm -rf` inside `/opt/cloud-portal`. The only deletion is `rm -rf` of the disposable checkout that block C itself created under `$BK`.

## A. Records directory and constants (writes only under `~/deploy-records`)

```bash
# BLOCK: A-prepare
( set -Eeuo pipefail; umask 077
  STAMP=$(date +%Y%m%d-%H%M%S)
  BK="$HOME/deploy-records/visual-$STAMP"
  mkdir -p "$HOME/deploy-records"
  mkdir "$BK"                      # no -p: fails if the directory already exists (overwrite guard)
  mkdir "$BK/state"
  set -o noclobber
  cat > "$BK/consts.sh" <<'EOF'
BASE=e44d4f0543adc3522edb12e3a4df2a8aad48a4c8
TARGET=5147723351b2672ec5c81fa4d7d1ba6a3d9828f2
EXPECT_TREE=69e6ec4ca740de904c1a5d051aca8e615924453e
EXPECT_BRANCH=codex/windows-rdp
EXPECT_CSS=4
EXPECT_HTML=5
APP=/opt/cloud-portal
PY=/opt/cloud-portal/venv/bin/python
SERVICE=cloud-portal
SITE=https://proxmoxportal.dyndns.org
REPO_URL=https://github.com/john-selwyn/cloud-portal
REMOTE_REF=design/visual-consistency-preview

die() { echo "ABORT: $*" >&2; exit 1; }

assert_clean_env() {   # inherited settings variables would override $APP/.env (load_dotenv never overrides)
  local bad
  bad=$(env | grep -E '^(DEBUG|SECRET_KEY|DJANGO_[A-Z_]*|DB_[A-Z_]*|ALLOWED_HOSTS|CSRF_[A-Z_]*|ALLOW_TEST_PAYMENT|PROVISIONING_[A-Z_]*|BILLING_API_SECRET|WINDOWS_[A-Z_]*|XENDIT_[A-Z_]*|HESTIA_[A-Z_]*|CUSTOMER_[A-Z_]*|EMAIL_[A-Z_]*|DEFAULT_FROM_EMAIL|MONITORING_[A-Z_]*|PYTHONPATH)=' | cut -d= -f1 | tr '\n' ' ' || true)
  [ -z "$bad" ] || die "inherited variable(s) would override $APP/.env: $bad -- open a fresh shell"
}
assert_tracked_clean() {
  [ -z "$(git -C "$APP" status --porcelain --untracked-files=no)" ] || die "tracked changes present in $APP"
}
assert_untracked_exact() {   # the ONLY allowed untracked paths: billing/ and monitoring-ca/
  local got want
  got=$(git -C "$APP" status --porcelain --untracked-files=normal | LC_ALL=C sort)
  want=$(printf '?? billing/\n?? monitoring-ca/')
  [ "$got" = "$want" ] || die "unexpected working-tree state in $APP: [$got]"
}
snapshot_untracked() {       # metadata only (path, type, size, mtime, mode); file contents are never read
  ( cd "$APP" && find billing monitoring-ca -printf '%p\t%y\t%s\t%T@\t%m\n' | LC_ALL=C sort )
}
assert_untracked_unchanged() {
  snapshot_untracked | diff -q "$BK/untracked-before.tsv" - >/dev/null || die "billing/ or monitoring-ca/ changed"
}
assert_scope() {             # $1 = repo dir. 4 CSS + 5 HTML, nothing else, identical tree
  local files css html other
  files=$(git -C "$1" diff --name-only "$BASE" "$TARGET")
  css=$(printf '%s\n' "$files" | grep -c '\.css$' || true)
  html=$(printf '%s\n' "$files" | grep -c '\.html$' || true)
  other=$(printf '%s\n' "$files" | grep -v -E '\.(css|html)$' || true)
  [ "$css" -eq "$EXPECT_CSS" ] && [ "$html" -eq "$EXPECT_HTML" ] || die "scope mismatch: $css css, $html html (expected $EXPECT_CSS and $EXPECT_HTML)"
  [ -z "$other" ] || die "non-CSS/HTML files changed: $other"
  [ "$(git -C "$1" rev-parse "$TARGET^{tree}")" = "$EXPECT_TREE" ] || die "target tree differs from the reviewed tree"
}
validate_backup() {
  local a="$BK/staticfiles.tar.gz" n m
  [ -s "$a" ] || die "backup archive missing or empty"
  ( cd "$BK" && sha256sum -c --quiet staticfiles.tar.gz.sha256 ) || die "backup checksum mismatch"
  tar -tzf "$a" > "$BK/staticfiles.list" || die "backup archive unreadable"
  for m in staticfiles/portal/portal.css staticfiles/portal/portal-modern.css staticfiles/portal/storefront.css staticfiles/portal/dashboard.css; do
    grep -qx "$m" "$BK/staticfiles.list" || die "backup is missing $m"
  done
  n=$(grep -vc '/$' "$BK/staticfiles.list" || true)
  [ "$n" -eq "$(cat "$BK/staticfiles.count")" ] || die "backup file count ($n) differs from the count recorded at backup time"
}
EOF
  printf 'STAMP=%s\nBK=%s\nRB=rollback/visual-pre-%s\n' "$STAMP" "$BK" "$STAMP" >> "$BK/consts.sh"
  echo "Records directory: $BK"
  echo "Copy that exact path into the BK= line of blocks B-F."
)
```

Each later block starts with a `BK=` line. Replace the example path with the one printed above. If it is wrong, the block aborts.

## B. Preflight on the production tree, backup, rollback branch

Read-only for the working tree. It writes only to `$BK`, plus one new Git branch ref (`rollback/visual-pre-<stamp>`) that pins the baseline commit.

```bash
# BLOCK: B-preflight
( set -Eeuo pipefail; umask 077
  BK="$HOME/deploy-records/visual-YYYYMMDD-HHMMSS"      # <- paste the path printed by block A
  [ -d "$BK/state" ] && [ -f "$BK/consts.sh" ] || { echo "ABORT: BK is wrong" >&2; exit 1; }
  . "$BK/consts.sh"
  trap 'rc=$?; [ $rc -eq 0 ] || echo "STOPPED (exit $rc). Nothing in the application tree was changed by this block." >&2' EXIT
  [ ! -e "$BK/state/preflight.ok" ] || die "preflight already completed for $BK (overwrite guard)"
  assert_clean_env
  cd "$APP"
  [ "$(git rev-parse HEAD)" = "$BASE" ] || die "wrong baseline: HEAD is $(git rev-parse HEAD)"
  [ "$(git branch --show-current)" = "$EXPECT_BRANCH" ] || die "unexpected branch: $(git branch --show-current)"
  assert_tracked_clean
  assert_untracked_exact
  [ -z "$(git stash list)" ] || die "git stash is not empty"
  for u in "$SERVICE" nginx; do systemctl is-active --quiet "$u" || die "$u is not active"; done
  [ -d staticfiles ] || die "$APP/staticfiles is missing"
  git rev-parse --verify --quiet "refs/heads/$RB" >/dev/null && die "rollback branch $RB already exists" || true

  snapshot_untracked > "$BK/untracked-before.tsv"
  [ -s "$BK/untracked-before.tsv" ] || die "billing/ or monitoring-ca/ snapshot is empty"
  git status --porcelain > "$BK/git-status-before.txt"
  git rev-parse HEAD > "$BK/baseline-sha.txt"

  set -o noclobber                                      # never overwrite an existing backup
  tar -czf "$BK/staticfiles.tar.gz" staticfiles
  find staticfiles -type f | wc -l > "$BK/staticfiles.count"
  ( cd "$BK" && sha256sum staticfiles.tar.gz > staticfiles.tar.gz.sha256 )
  validate_backup

  git branch "$RB" "$BASE"                              # named branch preserving the rollback commit
  [ "$(git rev-parse "refs/heads/$RB")" = "$BASE" ] || die "rollback branch does not point at the baseline"
  assert_tracked_clean; assert_untracked_exact; assert_untracked_unchanged
  echo "$BASE" > "$BK/state/preflight.ok"
  echo "PREFLIGHT OK. Backup: $BK/staticfiles.tar.gz  Rollback branch: $RB -> $BASE"
)
```

## C. Isolated verification (disposable checkout; production untouched)

The test environment is built with `env -i`, so **no inherited variable** (database, Xendit, provisioning, Hestia, email, `ALLOW_TEST_PAYMENT`, …) reaches Django. An empty `.env` inside the checkout stops `python-dotenv` from walking up to `~/.env` or any parent directory. The block then asserts, from inside Django, that the database is SQLite, its file lies inside the disposable checkout, the test database is in memory, and every integration setting is empty.

```bash
# BLOCK: C-isolated
( set -Eeuo pipefail; umask 077
  BK="$HOME/deploy-records/visual-YYYYMMDD-HHMMSS"      # <- same path as block B
  [ -d "$BK/state" ] && [ -f "$BK/consts.sh" ] || { echo "ABORT: BK is wrong" >&2; exit 1; }
  . "$BK/consts.sh"
  trap 'rc=$?; [ $rc -eq 0 ] || echo "STOPPED (exit $rc). Production was not touched. The disposable checkout (if any) is at $BK/verify-checkout." >&2' EXIT
  [ -f "$BK/state/preflight.ok" ] || die "run block B first"
  [ ! -e "$BK/state/isolated.ok" ] || die "isolated verification already passed for this run"
  CK="$BK/verify-checkout"
  [ ! -e "$CK" ] || die "$CK already exists (overwrite guard)"

  git clone --quiet --branch "$REMOTE_REF" "$REPO_URL" "$CK"
  cd "$CK"
  [ "$(git rev-parse HEAD)" = "$TARGET" ] || die "wrong target: HEAD is $(git rev-parse HEAD)"
  [ -z "$(git status --porcelain)" ] || die "fresh checkout is not clean"
  git merge-base --is-ancestor "$BASE" "$TARGET" || die "baseline is not an ancestor of the target"
  assert_scope "$CK"

  : > "$CK/.env"                                        # empty, gitignored: python-dotenv stops here
  isolated() {                                          # only these variables exist for the child process
    env -i PATH=/usr/bin:/bin HOME="$CK" LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
        CK="$CK" SECRET_KEY=isolated-check-only-not-secret DEBUG=True "$@"
  }
  isolated "$PY" - <<'PYEOF'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cloud_portal.settings")
import django
django.setup()
from django.conf import settings
from django.db import connection

ck = os.path.realpath(os.environ["CK"])
db = settings.DATABASES["default"]
assert db["ENGINE"] == "django.db.backends.sqlite3", "engine is %s" % db["ENGINE"]
assert connection.vendor == "sqlite", "vendor is %s" % connection.vendor
path = os.path.realpath(str(db["NAME"]))
assert path.startswith(ck + os.sep), "database path %s is outside %s" % (path, ck)
assert not db.get("HOST") and not db.get("USER") and not db.get("PASSWORD"), "network DB settings present"
assert not (db.get("TEST") or {}).get("NAME"), "test database is not in memory"
assert settings.DEBUG is True
assert os.path.realpath(str(settings.BASE_DIR)) == ck, "BASE_DIR is not the disposable checkout"
for name in ("PROVISIONING_API_URL", "BILLING_API_SECRET", "XENDIT_SECRET_API_KEY", "XENDIT_WEBHOOK_TOKEN",
             "XENDIT_BUSINESS_ID", "XENDIT_PUBLIC_BASE_URL", "HESTIA_API_URL", "HESTIA_API_USER", "HESTIA_API_PASSWORD"):
    assert getattr(settings, name) == "", "%s is not empty" % name
assert settings.ALLOW_TEST_PAYMENT is False
leaked = sorted(k for k in os.environ if k.startswith(("DB_", "XENDIT_", "PROVISIONING_", "HESTIA_", "BILLING_", "EMAIL_")))
assert not leaked, "leaked environment: %s" % leaked
print("ISOLATION OK: sqlite file=%s (inside checkout), test DB in memory, integrations empty" % path)
PYEOF
  isolated "$PY" manage.py check
  isolated "$PY" manage.py makemigrations --check --dry-run
  isolated "$PY" manage.py test portal -v1 > "$BK/isolated-tests.log" 2>&1 || { tail -30 "$BK/isolated-tests.log" >&2; die "tests failed (full log: $BK/isolated-tests.log)"; }
  grep -q '^Ran 309 tests' "$BK/isolated-tests.log" || die "unexpected test count (expected 309)"
  grep -q '^OK (skipped=2)' "$BK/isolated-tests.log" || die "expected 'OK (skipped=2)' (307 passed, 2 PostgreSQL-only skipped)"

  # production must be exactly as it was
  [ "$(git -C "$APP" rev-parse HEAD)" = "$BASE" ] || die "production HEAD changed"
  assert_tracked_clean; assert_untracked_exact; assert_untracked_unchanged
  cd "$HOME" && rm -rf "$CK"                            # the disposable checkout only
  echo "$TARGET" > "$BK/state/isolated.ok"
  echo "ISOLATED VERIFICATION OK: 309 ran, 307 passed, 2 skipped (PostgreSQL-only), in-memory SQLite. Log: $BK/isolated-tests.log"
)
```

Expected: `ISOLATION OK`, `309` tests, `OK (skipped=2)`. This proves the code on VM200's Python and Django against SQLite, **not** PostgreSQL concurrency behaviour (the two skipped tests need PostgreSQL).

## D. Deploy the code and collect static files — does NOT restart

Requires approval. Every guard is checked again at deploy time, then the tree is fast-forwarded. **Never `git pull`**: GitHub's `origin/codex/windows-rdp` (`289825f`) is not the deployed commit.

```bash
# BLOCK: D-deploy
( set -Eeuo pipefail
  BK="$HOME/deploy-records/visual-YYYYMMDD-HHMMSS"      # <- same path as block B
  [ -d "$BK/state" ] && [ -f "$BK/consts.sh" ] || { echo "ABORT: BK is wrong" >&2; exit 1; }
  . "$BK/consts.sh"
  trap 'rc=$?; [ $rc -eq 0 ] || echo "STOPPED (exit $rc). The service has NOT been restarted. If the tree or $APP/staticfiles changed, run block F (rollback); otherwise investigate." >&2' EXIT
  [ -f "$BK/state/preflight.ok" ] && [ -f "$BK/state/isolated.ok" ] || die "blocks B and C must both have passed"
  [ ! -e "$BK/state/deployed.ok" ] || die "already deployed for this run"
  assert_clean_env
  cd "$APP"
  [ "$(git rev-parse HEAD)" = "$BASE" ] || die "wrong baseline: HEAD is $(git rev-parse HEAD)"
  [ "$(git branch --show-current)" = "$EXPECT_BRANCH" ] || die "unexpected branch"
  assert_tracked_clean; assert_untracked_exact; assert_untracked_unchanged
  [ -z "$(git stash list)" ] || die "git stash is not empty"
  [ "$(git rev-parse "refs/heads/$RB")" = "$BASE" ] || die "rollback branch missing or moved"
  validate_backup

  git fetch --quiet origin "$REMOTE_REF"
  [ "$(git rev-parse FETCH_HEAD)" = "$TARGET" ] || die "fetched $(git rev-parse FETCH_HEAD), expected $TARGET"
  git merge-base --is-ancestor HEAD "$TARGET" || die "not a fast-forward"
  assert_scope "$APP"

  git merge --ff-only "$TARGET"
  [ "$(git rev-parse HEAD)" = "$TARGET" ] || die "HEAD is not the target after merge"
  assert_tracked_clean; assert_untracked_exact

  "$PY" manage.py check
  "$PY" manage.py migrate --plan | tee "$BK/migrate-plan.txt"
  grep -qi 'No planned migration operations' "$BK/migrate-plan.txt" || die "migrate --plan is not empty: this change must not need migrations. Do NOT run migrate."
  "$PY" manage.py collectstatic --noinput | tee "$BK/collectstatic.log"

  changed_static=$(git diff --name-only "$BASE" "$TARGET" -- portal/static)
  [ -n "$changed_static" ] || die "no static files in the diff"
  for f in $changed_static; do
    cmp -s "$f" "staticfiles/${f#portal/static/}" || die "collected file differs from source: $f"
    echo "identical: staticfiles/${f#portal/static/}"
  done
  assert_untracked_unchanged
  echo "$TARGET" > "$BK/state/deployed.ok"
  echo "CODE AND STATIC FILES IN PLACE at $TARGET. The service is NOT restarted yet: run block E."
)
```

There is a short window between this block and block E in which the running Gunicorn still serves its old (cached) templates against the new CSS. Run E immediately after D.

## E. Restart `cloud-portal` and verify

The restart is needed because Django caches templates when `DEBUG=False`. Nginx serves static files from disk and needs no reload.

```bash
# BLOCK: E-restart-verify
( set -Eeuo pipefail
  BK="$HOME/deploy-records/visual-YYYYMMDD-HHMMSS"      # <- same path as block B
  [ -d "$BK/state" ] && [ -f "$BK/consts.sh" ] || { echo "ABORT: BK is wrong" >&2; exit 1; }
  . "$BK/consts.sh"
  trap 'rc=$?; [ $rc -eq 0 ] || echo "STOPPED (exit $rc). Verification failed: use block F (rollback) unless you can explain the failure." >&2' EXIT
  [ -f "$BK/state/deployed.ok" ] || die "run block D first"
  [ ! -e "$BK/state/restarted.ok" ] || die "already restarted and verified for this run"
  assert_clean_env
  cd "$APP"
  [ "$(git rev-parse HEAD)" = "$TARGET" ] || die "HEAD is not the target"
  assert_tracked_clean; assert_untracked_exact

  sudo systemctl restart "$SERVICE"
  sleep 3
  systemctl is-active --quiet "$SERVICE" || die "$SERVICE is not active after restart"
  journalctl -u "$SERVICE" -n 40 --no-pager > "$BK/journal-after-restart.txt" || true
  ! grep -q 'Traceback' "$BK/journal-after-restart.txt" || die "traceback in the service journal ($BK/journal-after-restart.txt)"

  for p in / /plans/ /web-hosting/ /accounts/login/ /register/; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$SITE$p")
    [ "$code" = 200 ] || die "$p returned HTTP $code"
  done
  curl -fsS "$SITE/plans/" | grep -q 'customer-pages.css?v=consistency-2' || die "plans page does not reference the new stylesheet"
  for f in $(git diff --name-only "$BASE" "$TARGET" -- portal/static); do
    curl -fsS "$SITE/static/${f#portal/static/}" | cmp -s - "$f" || die "served file differs from source: $f"
    echo "served identical: ${f#portal/static/}"
  done
  assert_untracked_unchanged
  echo "$TARGET" > "$BK/state/restarted.ok"
  echo "DEPLOYED AND VERIFIED. Now do the manual phone-width check below."
)
```

Manual check (phone-width browser, signed in as a **test customer**; do not click Pay Now or any power button): Dashboard, My VPS, Orders, Invoices, Account, a VPS detail page, an order and an invoice page; signed out: Web Hosting and VPS Plans; staff `/management/`. Check for overlapping text, neat mobile navigation, a blue Provisioning badge on Dashboard and My VPS, and "vCPU / RAM / Storage" labels.

## F. Rollback (code, static files, restart; no database work)

Resets **nothing** unless all of these hold: the backup validates (checksum, readable archive, expected members, file count), the rollback branch still points at the baseline, `HEAD` is exactly the expected deployed SHA, the current branch is the expected one, and a fresh check shows **no tracked changes** and exactly the two known untracked directories.

```bash
# BLOCK: F-rollback
( set -Eeuo pipefail
  BK="$HOME/deploy-records/visual-YYYYMMDD-HHMMSS"      # <- same path as block B
  [ -d "$BK/state" ] && [ -f "$BK/consts.sh" ] || { echo "ABORT: BK is wrong" >&2; exit 1; }
  . "$BK/consts.sh"
  EXPECT_DEPLOYED="$TARGET"          # if you deployed a different (merged) commit, set its full SHA here
  trap 'rc=$?; [ $rc -eq 0 ] || echo "STOPPED (exit $rc). Do not retry blindly: read the ABORT line above and inspect git status and staticfiles first." >&2' EXIT
  [ -f "$BK/state/preflight.ok" ] || die "no preflight record: cannot roll back safely"
  [ ! -e "$BK/state/rolled-back.ok" ] || die "already rolled back for this run"
  assert_clean_env
  cd "$APP"

  validate_backup                                        # 1. backup is valid BEFORE anything changes
  [ "$(git rev-parse "refs/heads/$RB")" = "$BASE" ] || die "rollback branch $RB is missing or moved"
  [ "$(git rev-parse HEAD)" = "$EXPECT_DEPLOYED" ] || die "HEAD is $(git rev-parse HEAD), not the expected deployed SHA $EXPECT_DEPLOYED"
  [ "$(git branch --show-current)" = "$EXPECT_BRANCH" ] || die "unexpected branch: $(git branch --show-current)"
  assert_tracked_clean                                   # 2. fresh tracked-cleanliness check
  assert_untracked_exact

  git reset --hard "refs/heads/$RB"                      # tracked files only; untracked dirs are not touched
  [ "$(git rev-parse HEAD)" = "$BASE" ] || die "HEAD is not the baseline after reset"
  assert_tracked_clean; assert_untracked_exact

  tar -xzf "$BK/staticfiles.tar.gz" -C "$APP"            # previous collected files
  for f in $(git diff --diff-filter=A --name-only "$BASE" "$EXPECT_DEPLOYED" -- portal/static); do
    rm -f "staticfiles/${f#portal/static/}"              # files this change introduced
  done
  for f in $(git diff --diff-filter=M --name-only "$BASE" "$EXPECT_DEPLOYED" -- portal/static); do
    git show "$BASE:$f" | cmp -s - "staticfiles/${f#portal/static/}" || die "restored file does not match the baseline: $f"
    echo "restored: staticfiles/${f#portal/static/}"
  done
  [ "$(find staticfiles -type f | wc -l)" -eq "$(cat "$BK/staticfiles.count")" ] || die "staticfiles file count differs from the backup"
  assert_untracked_unchanged

  sudo systemctl restart "$SERVICE"
  sleep 3
  systemctl is-active --quiet "$SERVICE" || die "$SERVICE is not active after rollback"
  for p in / /plans/ /web-hosting/ /accounts/login/; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "$SITE$p")
    [ "$code" = 200 ] || die "$p returned HTTP $code after rollback"
  done
  ! curl -fsS "$SITE/plans/" | grep -q 'customer-pages.css' || die "plans page still references the new stylesheet"
  echo "$BASE" > "$BK/state/rolled-back.ok"
  echo "ROLLED BACK to $BASE. The deployed commit remains reachable in git reflog and objects."
)
```

If a step in block F aborts after `git reset`, stop: the tree is already at the baseline, so re-check `git status`, the backup and `staticfiles` by hand rather than re-running the block.

## G. After a successful deploy

Keep `~/deploy-records/visual-<stamp>/` (backup, logs, checksums, state markers) and the branch `rollback/visual-pre-<stamp>` for at least a week. Nothing here deletes them. When you want to remove the branch: `git -C /opt/cloud-portal branch -D rollback/visual-pre-<stamp>`. The VM200 `billing/` and `monitoring-ca/` directories must still show as the only untracked paths in `git status`.

## What this does not cover

Provisioning, payments, database migrations, PostgreSQL behaviour, or anything inside `billing/` and `monitoring-ca/` (their contents are never read; only path/size/mtime metadata is compared before and after).

## How this runbook was tested (rev 2)

Every block was extracted from this file and run in a disposable sandbox that mimics VM200: a clone at the baseline on `codex/windows-rdp`, untracked `billing/` and `monitoring-ca/`, a real `collectstatic`, a local Git remote holding the target, and **fake** `sudo`, `systemctl`, `journalctl` and `curl`. Results:

- Full path A → B → C → D → E → F passed (309 tests ran, 307 passed, 2 skipped; `migrate --plan` printed `No planned migration operations`; rollback restored the baseline tree and 143 static files).
- Blocks stopped before changing anything on: dirty tracked file, extra untracked path, modified `billing/`, corrupted checksum, wrong backup file count, moved remote (wrong target SHA), moved rollback branch, wrong branch, inherited `DEBUG`, non-empty migration plan.
- Block D stopped on a failed `collectstatic` and on a failed CSS comparison. Rollback refused on: dirty tracked file, missing backup, HEAD differing from the expected deployed SHA.
- Block C still passed with `DB_HOST`, `DB_PASSWORD`, `XENDIT_*`, `PROVISIONING_*` and `ALLOW_TEST_PAYMENT` exported in the parent shell.

**Not tested:** real VM200 (systemd, Nginx, Gunicorn, PostgreSQL, sudo rules, real HTTP). Block B/E assumptions about those come from the repo docs and must be confirmed on the host.
