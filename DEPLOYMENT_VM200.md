# VM200 deployment and rollback — visual consistency preview (rev 3 — review only)

**Status: REVIEW ONLY; DEPLOYMENT BLOCKED. No production action is authorized by this document.**

VM200 is now verified at `7fa0023af434929b27d243e73a9a3a11ef8b0dd6`, with migration `0013_ubuntu_server_operating_system` applied and Ubuntu Server ordering enabled (23 October 2026). PR #9 remains at `5147723351b2672ec5c81fa4d7d1ba6a3d9828f2`, based on the older accounts release `e44d4f0`. **That target is not a descendant of the deployed release.** Its complete tree does not contain the Ubuntu Server changes. Do not reset production to it or substitute an unreviewed merge commit.

The constants intentionally pin this incompatible pair. Block B rejects it **before taking a backup or changing a branch**, and D checks again before touching application files. A new target preserving `7fa0023` must be prepared and reviewed separately; then its full SHA, complete tree, exact nine-file diff and test expectations must be re-pinned here. Do not bypass the guard or change BASE back to `e44d4f0`. The evidence branch must stay outside the application PR.

The blocks below are proposed operational instructions for that subsequent approved release, not commands to execute now. Stop at the first `ABORT`. No merge, deployment, migration or service restart was performed while correcting this document.

This file lives on the `evidence/visual-consistency-preview` branch. It is not part of application PR #9 (`design/visual-consistency-preview`) and must never be added to it.

| | |
|---|---|
| Baseline (latest verified deployed) | `7fa0023af434929b27d243e73a9a3a11ef8b0dd6`, local branch `codex/windows-rdp`; portal migration 0013 applied |
| Reviewed visual target — blocked for deployment | `5147723351b2672ec5c81fa4d7d1ba6a3d9828f2` (PR #9 head); original review baseline `e44d4f0543adc3522edb12e3a4df2a8aad48a4c8` |
| Target tree | `69e6ec4ca740de904c1a5d051aca8e615924453e` — identifies the reviewed visual snapshot only; no alternate SHA is accepted |
| Scope | **9 files, presentation only: 4 stylesheets + 5 templates** (verified against the original review baseline: 1 added + 3 modified CSS, 5 modified HTML). CSS: `customer-pages.css` (new), `dashboard.css`, `portal-modern.css`, `storefront.css`. HTML: `base.html`, `dashboard.html`, `my_vps.html`, `orders.html`, `plans.html` (all under `portal/`). The blocks below enforce 4 CSS + 5 HTML + 0 other files. |
| Not changed | Python, settings, models, migrations, forms, URLs, JavaScript, `.env`, database. **No migrations.** |

Latest owner-supplied VM200 output confirms the directory, service activity and source/migrations listed above. Repository operational references (`deploy/CLOUD_PORTAL_RENAME.md`, `deploy/CUSTOMER_ACCOUNTS.md`) describe: VM200 `/opt/cloud-portal`, user `ict-tech`, `cloud-portal.service` (Gunicorn, `127.0.0.1:8001`), Nginx site `cloud-portal`, assets in `/opt/cloud-portal/staticfiles`, public URL `https://proxmoxportal.dyndns.org`. The public HTTPS URL and live HTTP behaviour were not re-verified during this runbook review; confirm them separately. Block B checks hostname, service state, branch, source and exact release compatibility.

## How the blocks are built (read once)

- **Every block is a `( … )` subshell with `set -Eeuo pipefail`.** Variables, `cd`, `DEBUG` and `SECRET_KEY` cannot leak into your login shell or into later production commands. Block C's test settings exist only inside its own `env -i` child process.
- **Fail closed:** any failed guard calls `die` (prints `ABORT: …`, exits 1). Blocks D–F also print `STOPPED` on any non-zero exit. A block only writes its marker file (`$BK/state/*.ok`) when every step passed, and the next block refuses to start without the previous marker.
- **Production blocks refuse to run if the shell has inherited settings variables** (`DEBUG`, `SECRET_KEY`, `DB_*`, `XENDIT_*`, `PROVISIONING_*`, …). `settings.py` calls `load_dotenv()` without `override`, so an inherited variable would silently beat `/opt/cloud-portal/.env`. Open a fresh shell if a block reports one.
- **Deploy/rollback explicitly use `umask 022`**, so an inherited restrictive umask cannot make new static files unreadable by Nginx. The records directory remains private (mode 700).
- Blocks never run `git clean`, `git stash`, `git add`, `git checkout -- .` or recursive deletion inside `/opt/cloud-portal`. The disposable checkout is retained for diagnosis; this document does not delete it. Rollback resets tracked files only after the guards below pass.

## A. Records directory and constants (writes only under `~/deploy-records`)

```bash
# BLOCK: A-prepare
( set -Eeuo pipefail; umask 077
  STAMP=$(date +%Y%m%d-%H%M%S)
  BK="$HOME/deploy-records/visual-$STAMP"
  [ "$(hostname)" = cloud-portal ] || { echo "ABORT: run only on VM200/cloud-portal" >&2; exit 1; }
  mkdir -p "$HOME/deploy-records"
  mkdir "$BK"                      # no -p: fails if the directory already exists (overwrite guard)
  mkdir "$BK/state"
  set -o noclobber
  cat > "$BK/consts.sh" <<'EOF'
BASE=7fa0023af434929b27d243e73a9a3a11ef8b0dd6
REVIEW_BASE=e44d4f0543adc3522edb12e3a4df2a8aad48a4c8
TARGET=5147723351b2672ec5c81fa4d7d1ba6a3d9828f2
EXPECT_TREE=69e6ec4ca740de904c1a5d051aca8e615924453e
EXPECT_BRANCH=codex/windows-rdp
EXPECT_CSS=4
EXPECT_HTML=5
EXPECT_TESTS=309
EXPECT_SKIPS=2
# 309/2 describe the old reviewed visual snapshot. Re-pin after reviewing a
# target preserving 7fa0023 (that release currently contains 314 portal tests).
APP=/opt/cloud-portal
PY=/opt/cloud-portal/venv/bin/python
SERVICE=cloud-portal
SITE=https://proxmoxportal.dyndns.org
REPO_URL=https://github.com/john-selwyn/cloud-portal
REMOTE_REF=design/visual-consistency-preview

die() { echo "ABORT: $*" >&2; exit 1; }

assert_clean_env() {   # inherited settings variables would override $APP/.env (load_dotenv never overrides)
  local bad
  bad=$(compgen -e | LC_ALL=C sort | grep -E '^(DEBUG|SECRET_KEY|DJANGO_.*|DB_.*|DATABASE_.*|PG.*|ALLOWED_HOSTS|CSRF_.*|ALLOW_TEST_PAYMENT|UBUNTU_SERVER_.*|PROVISIONING_.*|BILLING_.*|WINDOWS_.*|XENDIT_.*|HESTIA_.*|CUSTOMER_.*|EMAIL_.*|DEFAULT_FROM_EMAIL|MONITORING_.*|PYTHON.*)$' || true)
  [ -z "$bad" ] || die "inherited variable(s) would override $APP/.env: $bad -- open a fresh shell"
}
assert_tracked_clean() {
  local status
  status=$(git -C "$APP" status --porcelain --untracked-files=no) || die "git status failed"
  [ -z "$status" ] || die "tracked changes present in $APP"
}
assert_untracked_exact() {   # the ONLY allowed untracked paths: billing/ and monitoring-ca/
  local got want
  got=$(git -C "$APP" status --porcelain --untracked-files=normal | LC_ALL=C sort) || die "git status failed"
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
  files=$(git -C "$1" diff --name-only "$BASE" "$TARGET") || die "git diff failed"
  css=$(printf '%s\n' "$files" | grep -c '\.css$' || true)
  html=$(printf '%s\n' "$files" | grep -c '\.html$' || true)
  other=$(printf '%s\n' "$files" | grep -v -E '\.(css|html)$' || true)
  [ "$css" -eq "$EXPECT_CSS" ] && [ "$html" -eq "$EXPECT_HTML" ] || die "scope mismatch: $css css, $html html (expected $EXPECT_CSS and $EXPECT_HTML)"
  [ -z "$other" ] || die "non-CSS/HTML files changed: $other"
  local expected
  expected=$(printf '%s\n' portal/static/portal/customer-pages.css portal/static/portal/dashboard.css portal/static/portal/portal-modern.css portal/static/portal/storefront.css portal/templates/portal/base.html portal/templates/portal/dashboard.html portal/templates/portal/my_vps.html portal/templates/portal/orders.html portal/templates/portal/plans.html | LC_ALL=C sort)
  [ "$files" = "$expected" ] || die "changed paths differ from the reviewed nine-file scope"
  [ "$(git -C "$1" diff --diff-filter=A --name-only "$BASE" "$TARGET")" = portal/static/portal/customer-pages.css ] || die "unexpected added paths"
  [ -z "$(git -C "$1" diff --diff-filter=DRCTUXB --name-only "$BASE" "$TARGET")" ] || die "unexpected file status"
  [ "$(git -C "$1" rev-parse "$TARGET^{tree}")" = "$EXPECT_TREE" ] || die "target tree differs from the reviewed tree"
}
assert_release() {
  local repo="$1" fetched
  [[ "$BASE" =~ ^[0-9a-f]{40}$ && "$TARGET" =~ ^[0-9a-f]{40}$ && "$EXPECT_TREE" =~ ^[0-9a-f]{40}$ ]] || die "release constants are not full object IDs"
  git -C "$repo" fetch --quiet --no-tags origin "$REMOTE_REF" || die "target fetch failed"
  fetched=$(git -C "$repo" rev-parse --verify 'FETCH_HEAD^{commit}') || die "cannot resolve fetched target"
  [ "$fetched" = "$TARGET" ] || die "remote target moved: expected $TARGET, fetched $fetched"
  git -C "$repo" merge-base --is-ancestor "$BASE" "$TARGET" || die "reviewed target omits the current production baseline; release is BLOCKED"
  assert_scope "$repo"
}
assert_collected_css() {
  local files f
  files=$(git -C "$APP" diff --name-only "$BASE" "$TARGET" -- portal/static) || die "static diff failed"
  [ -n "$files" ] || die "no reviewed static files"
  for f in $files; do
    cmp -s "$APP/$f" "$APP/staticfiles/${f#portal/static/}" || die "collected file differs from source: $f"
  done
}
validate_backup() {
  local a="$BK/staticfiles.tar.gz"
  [ -f "$a" ] && [ ! -L "$a" ] && [ -s "$a" ] || die "backup archive missing, linked or empty"
  [ -f "$BK/staticfiles.tar.gz.sha256" ] && [ -f "$BK/staticfiles.count" ] || die "backup metadata missing"
  ( cd "$BK" && sha256sum -c --quiet staticfiles.tar.gz.sha256 ) || die "backup checksum mismatch"
  "$PY" - "$a" "$BK/staticfiles.count" "$BK/staticfiles.tar.gz.sha256" <<'BACKUP_PY' || die "backup validation failed"
import hashlib, pathlib, sys, tarfile
archive, count_path, checksum_path = sys.argv[1:]
checksum = pathlib.Path(checksum_path).read_text().split()
assert len(checksum) == 2 and checksum[1].removeprefix("*") == "staticfiles.tar.gz", "wrong checksum member"
with open(archive, "rb") as source:
    digest = hashlib.file_digest(source, "sha256").hexdigest()
assert digest == checksum[0], "archive digest mismatch"
with tarfile.open(archive, "r:gz") as tar:
    members = tar.getmembers()
    names = set()
    files = 0
    for member in members:
        p = pathlib.PurePosixPath(member.name)
        assert not p.is_absolute() and p.parts and p.parts[0] == "staticfiles"
        assert ".." not in p.parts and "\\" not in member.name
        assert member.name not in names, "duplicate archive member"
        assert member.isdir() or member.isfile(), "links/special files are not allowed"
        names.add(member.name)
        if member.isfile():
            files += 1
            stream = tar.extractfile(member)
            while stream.read(1024 * 1024):
                pass
    assert files == int(pathlib.Path(count_path).read_text()), "file count mismatch"
    for name in ("portal.css", "portal-modern.css", "storefront.css", "dashboard.css"):
        assert "staticfiles/portal/" + name in names, "required stylesheet missing"
BACKUP_PY
}
assert_readonly_plan() {
  PGOPTIONS='-c default_transaction_read_only=on -c lock_timeout=5s -c statement_timeout=30s' "$PY" - <<'PLAN_PY' || die "production settings or migration-plan check failed; do not run migrations"
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cloud_portal.settings")
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
assert settings.DEBUG is False, "production DEBUG must be False"
assert str(settings.STATIC_ROOT) == "/opt/cloud-portal/staticfiles"
assert connection.vendor == "postgresql", "unexpected production DB engine"
with connection.cursor() as cursor:
    cursor.execute("SELECT current_database(), current_setting('transaction_read_only')")
    assert cursor.fetchone() == ("cloud_portal_db", "on"), "wrong DB or writable check"
executor = MigrationExecutor(connection)
assert not executor.migration_plan(executor.loader.graph.leaf_nodes()), "pending migration plan"
connection.close()
print("Read-only production check: no planned migration operations")
PLAN_PY
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
  [ "$(hostname)" = cloud-portal ] || die "wrong host"
  [ -d staticfiles ] && [ ! -L staticfiles ] || die "$APP/staticfiles missing or symlinked"
  assert_release "$APP"
  "$PY" manage.py check || die "Django check failed"
  assert_readonly_plan
  git rev-parse --verify --quiet "refs/heads/$RB" >/dev/null && die "rollback branch $RB already exists" || true

  snapshot_untracked > "$BK/untracked-before.tsv"
  [ -s "$BK/untracked-before.tsv" ] || die "billing/ or monitoring-ca/ snapshot is empty"
  git status --porcelain > "$BK/git-status-before.txt"
  git rev-parse HEAD > "$BK/baseline-sha.txt"

  set -o noclobber                                      # never overwrite an existing backup
  tar -czf "$BK/staticfiles.tar.gz" staticfiles || die "static backup failed"
  find staticfiles -type f | wc -l > "$BK/staticfiles.count"
  ( cd "$BK" && sha256sum staticfiles.tar.gz > staticfiles.tar.gz.sha256 )
  validate_backup

  git branch "$RB" "$BASE" || die "could not preserve rollback branch"
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
        CK="$CK" PYTHON_DOTENV_DISABLED=1 SECRET_KEY=isolated-check-only-not-secret DEBUG=True "$@"
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
assert not db.get("HOST") and not db.get("PORT") and not db.get("USER") and not db.get("PASSWORD"), "network DB settings present"
assert not db.get("OPTIONS"), "unexpected database OPTIONS"
assert set(settings.DATABASES) == {"default"}, "unexpected extra database alias"
assert not (db.get("TEST") or {}).get("NAME"), "test database NAME override present"
assert connection.creation._get_test_db_name() == "file:memorydb_default?mode=memory&cache=shared", "test DB would not be in memory"
assert settings.DEBUG is True
assert os.path.realpath(str(settings.BASE_DIR)) == ck, "BASE_DIR is not the disposable checkout"
for name in ("PROVISIONING_API_URL", "BILLING_API_SECRET", "XENDIT_SECRET_API_KEY", "XENDIT_WEBHOOK_TOKEN",
             "XENDIT_BUSINESS_ID", "XENDIT_PUBLIC_BASE_URL", "HESTIA_API_URL", "HESTIA_API_USER", "HESTIA_API_PASSWORD"):
    assert getattr(settings, name, None) == "", "%s is not empty" % name
assert settings.ALLOW_TEST_PAYMENT is False
assert settings.CUSTOMER_EMAIL_ENABLED is False
assert getattr(settings, "UBUNTU_SERVER_ORDERING_ENABLED", False) is False
leaked = sorted(k for k in os.environ if k.startswith(("DB_", "XENDIT_", "PROVISIONING_", "HESTIA_", "BILLING_", "EMAIL_")))
assert not leaked, "leaked environment: %s" % leaked
print("ISOLATION OK: sqlite file=%s (inside checkout), test DB in memory, integrations empty" % path)
PYEOF
  isolated "$PY" manage.py check || die "isolated Django check failed"
  isolated "$PY" manage.py makemigrations --check --dry-run || die "isolated migration consistency check failed"
  isolated "$PY" manage.py test portal -v1 > "$BK/isolated-tests.log" 2>&1 || { tail -30 "$BK/isolated-tests.log" >&2; die "tests failed (full log: $BK/isolated-tests.log)"; }
  grep -q "^Ran $EXPECT_TESTS tests" "$BK/isolated-tests.log" || die "unexpected test count (expected $EXPECT_TESTS)"
  grep -qx "OK (skipped=$EXPECT_SKIPS)" "$BK/isolated-tests.log" || die "unexpected test result/skips"

  # production must be exactly as it was
  [ "$(git -C "$APP" rev-parse HEAD)" = "$BASE" ] || die "production HEAD changed"
  assert_tracked_clean; assert_untracked_exact; assert_untracked_unchanged
  # Retain this exact disposable checkout and log for inspection; no recursive deletion.
  echo "$TARGET" > "$BK/state/isolated.ok"
  echo "ISOLATED VERIFICATION OK: $EXPECT_TESTS ran, $EXPECT_SKIPS skipped (PostgreSQL-only), in-memory SQLite. Log: $BK/isolated-tests.log"
)
```

Expected: `ISOLATION OK`, `309` tests, `OK (skipped=2)`. This proves the code on VM200's Python and Django against SQLite, **not** PostgreSQL concurrency behaviour (the two skipped tests need PostgreSQL).

## D. Deploy the code and collect static files — does NOT restart

Requires approval. Every guard is checked again at deploy time, then the tree is fast-forwarded. **Never `git pull`**: GitHub's `origin/codex/windows-rdp` (`289825f`) is not the deployed commit.

```bash
# BLOCK: D-deploy
( set -Eeuo pipefail; umask 022
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

  assert_release "$APP"
  "$PY" manage.py check || die "baseline Django check failed"
  assert_readonly_plan

  git merge --ff-only "$TARGET" || die "fast-forward failed"
  [ "$(git rev-parse HEAD)" = "$TARGET" ] || die "HEAD is not the target after merge"
  assert_tracked_clean; assert_untracked_exact

  "$PY" manage.py check || die "target Django check failed"
  assert_readonly_plan
  "$PY" manage.py collectstatic --noinput | tee "$BK/collectstatic.log" || die "collectstatic failed; do not restart"

  changed_static=$(git diff --name-only "$BASE" "$TARGET" -- portal/static) || die "static diff failed"
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
  [ "$(git branch --show-current)" = "$EXPECT_BRANCH" ] || die "unexpected branch"
  assert_tracked_clean; assert_untracked_exact; assert_untracked_unchanged
  validate_backup
  assert_collected_css

  sudo systemctl restart "$SERVICE" || die "portal restart failed"
  sleep 3
  systemctl is-active --quiet "$SERVICE" || die "$SERVICE is not active after restart"
  journalctl -u "$SERVICE" --since '2 minutes ago' --no-pager > "$BK/journal-after-restart.txt" || die "cannot read service journal"
  ! grep -q 'Traceback' "$BK/journal-after-restart.txt" || die "traceback in the service journal ($BK/journal-after-restart.txt)"

  for p in / /plans/ /web-hosting/ /accounts/login/ /register/; do
    code=$(curl --connect-timeout 10 --max-time 30 -sS -o /dev/null -w '%{http_code}' "$SITE$p") || die "HTTP request failed: $p"
    [ "$code" = 200 ] || die "$p returned HTTP $code"
  done
  curl --connect-timeout 10 --max-time 30 -fsS "$SITE/plans/" -o "$BK/plans-after.html" || die "plans request failed"
  grep -q 'customer-pages.css?v=consistency-2' "$BK/plans-after.html" || die "plans page does not reference the new stylesheet"
  changed_static=$(git diff --name-only "$BASE" "$TARGET" -- portal/static) || die "static diff failed"
  for f in $changed_static; do
    curl --connect-timeout 10 --max-time 30 -fsS "$SITE/static/${f#portal/static/}" -o "$BK/served-css.tmp" || die "static request failed: $f"
    cmp -s "$BK/served-css.tmp" "$f" || die "served file differs from source: $f"
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
( set -Eeuo pipefail; umask 022
  BK="$HOME/deploy-records/visual-YYYYMMDD-HHMMSS"      # <- same path as block B
  [ -d "$BK/state" ] && [ -f "$BK/consts.sh" ] || { echo "ABORT: BK is wrong" >&2; exit 1; }
  . "$BK/consts.sh"
  EXPECT_DEPLOYED="$TARGET"          # exact pinned SHA only; no alternate/merged-commit bypass
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
  assert_untracked_unchanged
  assert_scope "$APP"

  git reset --hard "refs/heads/$RB" || die "tracked-file reset failed"
  [ "$(git rev-parse HEAD)" = "$BASE" ] || die "HEAD is not the baseline after reset"
  assert_tracked_clean; assert_untracked_exact

  tar -xzf "$BK/staticfiles.tar.gz" -C "$APP" || die "static restore failed after reset; stop and inspect"
  added_static=$(git diff --diff-filter=A --name-only "$BASE" "$EXPECT_DEPLOYED" -- portal/static) || die "added static diff failed"
  tar -tzf "$BK/staticfiles.tar.gz" > "$BK/restore-members.txt" || die "cannot list validated archive"
  for f in $added_static; do
    collected="staticfiles/${f#portal/static/}"
    # Retain a pre-existing collected file even if its source was new to Git.
    if ! grep -Fxq "$collected" "$BK/restore-members.txt"; then
      rm -f -- "$collected" || die "cannot remove introduced static file: $collected"
    fi
  done
  tar -dzf "$BK/staticfiles.tar.gz" -C "$APP" || die "restored static files differ from the validated backup"
  [ "$(find staticfiles -type f | wc -l)" -eq "$(cat "$BK/staticfiles.count")" ] || die "staticfiles file count differs from the backup"
  assert_untracked_unchanged

  sudo systemctl restart "$SERVICE" || die "rollback restart failed"
  sleep 3
  systemctl is-active --quiet "$SERVICE" || die "$SERVICE is not active after rollback"
  for p in / /plans/ /web-hosting/ /accounts/login/; do
    code=$(curl --connect-timeout 10 --max-time 30 -sS -o /dev/null -w '%{http_code}' "$SITE$p") || die "HTTP request failed: $p"
    [ "$code" = 200 ] || die "$p returned HTTP $code after rollback"
  done
  curl --connect-timeout 10 --max-time 30 -fsS "$SITE/plans/" -o "$BK/plans-rollback.html" || die "rollback plans request failed"
  if grep -q 'customer-pages.css' "$BK/plans-rollback.html"; then die "plans page still references the new stylesheet"; fi
  echo "$BASE" > "$BK/state/rolled-back.ok"
  echo "ROLLED BACK to $BASE. The deployed commit remains reachable in git reflog and objects."
)
```

If a step in block F aborts after `git reset`, stop: the tree is already at the baseline, so re-check `git status`, the backup and `staticfiles` by hand rather than re-running the block.

## G. After a successful deploy

Keep `~/deploy-records/visual-<stamp>/` (backup, logs, checksums, state markers) and the branch `rollback/visual-pre-<stamp>` for at least a week. Nothing here deletes them. No rollback-branch deletion is authorized by this review document; retain the named ref and records until separately reviewed cleanup. The VM200 `billing/` and `monitoring-ca/` directories must still show as the only untracked paths in `git status`.

## What this does not cover

Provisioning, payments, database migrations, PostgreSQL behaviour, or anything inside `billing/` and `monitoring-ca/` (their contents are never read; only path/size/mtime metadata is compared before and after).

## Verification provenance and limitations

The rev-2 author reported a Linux sandbox full-path test with 309 SQLite tests (307 passed, two PostgreSQL-only skips), mocked systemd/HTTP and negative cases. That report is historical, not a new live verification and not evidence of compatibility with current VM200 `7fa0023`.

Rev-3 verification results are recorded in the accompanying `RUNBOOK_REVIEW_VM200.md`. No block was run on VM200. No application merge, database migration, deployment or service restart is authorized or performed by this documentation work. The pinned production baseline and reviewed target remain incompatible; passing syntax or fixture tests cannot remove that release blocker.
