# VM200 deployment and rollback — visual consistency preview

**Status: PREPARED ONLY. Nothing has been merged, deployed, migrated or restarted.** Run these steps only after explicit approval.

- Baseline (currently deployed, per VM200 output): `e44d4f0543adc3522edb12e3a4df2a8aad48a4c8`, local branch `codex/windows-rdp`
- Target: `5147723351b2672ec5c81fa4d7d1ba6a3d9828f2` (branch `design/visual-consistency-preview`). If the PR is merged first, use the merged commit SHA instead and compare it to this one (`git diff 5147723 <merged-sha>` should be empty for these files).
- Changes: 4 stylesheets and 5 templates under `portal/`. **No migrations, no model/Python/settings change, no `.env` change, no database change.**
- Facts below come from the repository's `deploy/CLOUD_PORTAL_RENAME.md` (12 Oct) and `CUSTOMER_ACCOUNTS.md` (20 Oct): VM200 `/opt/cloud-portal`, user `ict-tech`, `cloud-portal.service` (Gunicorn 3 workers, `127.0.0.1:8001`), Nginx site `cloud-portal`, assets in `/opt/cloud-portal/staticfiles`, public URL `https://proxmoxportal.dyndns.org`. Confirm each on VM200 before relying on it.

## Hard rules

1. **Preserve `billing/` and `monitoring-ca/`** (untracked). Never run `git clean`, `git stash -u`/`--include-untracked`, `git checkout -- .`, `git add -A`, or `rm -rf` on the checkout.
2. **Do not `git pull`.** GitHub's `origin/codex/windows-rdp` (`289825f`) is not the deployed commit (`e44d4f0`); pulling would bring in unreviewed changes. Use the exact fast-forward below.
3. Do not touch `.env`, the database, `migrate`, payment or provisioning commands, or other services.

## 0. Pre-checks (read-only) on VM200 as `ict-tech`

```bash
cd /opt/cloud-portal
git rev-parse HEAD                       # expect e44d4f0543adc3522edb12e3a4df2a8aad48a4c8
git branch --show-current                # expect codex/windows-rdp
git status --porcelain=v1                # expect EXACTLY: "?? billing/" and "?? monitoring-ca/"
git status --porcelain=v1 --untracked-files=no   # expect empty (no tracked changes)
git stash list                           # expect empty
systemctl is-active cloud-portal nginx   # expect active / active
```

**Stop** if HEAD differs, tracked changes exist, or any other untracked path appears.

Record rollback information (outside the repository):

```bash
mkdir -p ~/deploy-records && D=$(date +%F)
git rev-parse HEAD > ~/deploy-records/rollback-sha-$D.txt
tar -czf ~/deploy-records/staticfiles-pre-visual-$D.tar.gz -C /opt/cloud-portal staticfiles
ls -l ~/deploy-records/ && tar -tzf ~/deploy-records/staticfiles-pre-visual-$D.tar.gz | head -3
```

## 1. Fresh-checkout verification (isolated; does not touch `/opt/cloud-portal`)

```bash
cd ~ && git clone --branch design/visual-consistency-preview https://github.com/john-selwyn/cloud-portal cloud-portal-visual-check
cd cloud-portal-visual-check
git rev-parse HEAD                                        # must equal 5147723351b2672ec5c81fa4d7d1ba6a3d9828f2
git status --porcelain                                    # expect empty
git fetch origin e44d4f0543adc3522edb12e3a4df2a8aad48a4c8 2>/dev/null || git fetch origin feature/customer-accounts
git diff --name-only e44d4f0543adc3522edb12e3a4df2a8aad48a4c8 HEAD | grep -v -E '\.(html|css)$' || echo "only html/css changed"
# Tests on a throwaway SQLite database (DEBUG=True selects SQLite per README; no .env exists in this clone)
export SECRET_KEY=check-only-not-secret DEBUG=True
/opt/cloud-portal/venv/bin/python manage.py check
/opt/cloud-portal/venv/bin/python manage.py makemigrations --check --dry-run     # No changes detected
/opt/cloud-portal/venv/bin/python manage.py test portal                          # expect 309 tests, OK (skipped=2)
cd ~ && rm -rf cloud-portal-visual-check
```

Expected: 309 tests OK with 2 skipped (PostgreSQL-only). This proves the code on VM200's own Python/Django, **not** PostgreSQL behaviour.

## 2. Deploy (requires explicit approval)

```bash
cd /opt/cloud-portal
git fetch origin design/visual-consistency-preview
test "$(git rev-parse FETCH_HEAD)" = 5147723351b2672ec5c81fa4d7d1ba6a3d9828f2 && echo "target SHA ok"
git merge-base --is-ancestor HEAD FETCH_HEAD && echo "fast-forward possible"
git merge --ff-only FETCH_HEAD
git rev-parse HEAD                       # 5147723351b2672ec5c81fa4d7d1ba6a3d9828f2
git status --porcelain=v1                # still ONLY "?? billing/" and "?? monitoring-ca/"
ls -d billing monitoring-ca              # both still present
```

Collect static files (do **not** use `--clear`):

```bash
/opt/cloud-portal/venv/bin/python manage.py check
/opt/cloud-portal/venv/bin/python manage.py migrate --plan          # expect: No planned migration operations
/opt/cloud-portal/venv/bin/python manage.py collectstatic --noinput # reports files copied (new/changed CSS only)
for f in customer-pages dashboard portal-modern storefront; do
  cmp portal/static/portal/$f.css staticfiles/portal/$f.css && echo "$f.css identical"
done
```

Restart is needed because Django caches templates when `DEBUG=False`:

```bash
sudo systemctl restart cloud-portal
systemctl is-active cloud-portal                 # active
journalctl -u cloud-portal -n 30 --no-pager      # no tracebacks
```

Nginx serves static files from disk; no Nginx reload is needed.

## 3. Verify

```bash
B=https://proxmoxportal.dyndns.org
for p in / /plans/ /web-hosting/ /accounts/login/ /register/; do curl -s -o /dev/null -w "%{http_code} $p\n" $B$p; done   # all 200
curl -s $B/plans/ | grep -o 'customer-pages.css?v=consistency-2'      # present
curl -sI "$B/static/portal/customer-pages.css?v=consistency-2" | head -1   # HTTP 200
curl -s "$B/static/portal/customer-pages.css" | grep -c 'Shared VPS card'   # 1 or more
```

Manual, on a phone-width browser, signed in as a **test customer** (do not click Pay Now or any power button): Dashboard, My VPS, Orders, Invoices, Account, a VPS detail page, an order/invoice page; signed out: Web Hosting and VPS Plans; staff `/management/`. Check: no overlapping text, mobile navigation is neat, Provisioning badge is blue on Dashboard and My VPS, labels read vCPU / RAM / Storage.

## 4. Rollback (code, static files, restart; no database work)

```bash
cd /opt/cloud-portal
D=<date used in step 0>
B=https://proxmoxportal.dyndns.org
test "$(cat ~/deploy-records/rollback-sha-$D.txt)" = e44d4f0543adc3522edb12e3a4df2a8aad48a4c8 && echo "rollback SHA ok"
git status --porcelain=v1 --untracked-files=no       # expect empty before resetting
git reset --hard e44d4f0543adc3522edb12e3a4df2a8aad48a4c8   # tracked files only; untracked billing/ and monitoring-ca/ are not touched
git rev-parse HEAD
tar -xzf ~/deploy-records/staticfiles-pre-visual-$D.tar.gz -C /opt/cloud-portal   # restores previous collected files
rm -f staticfiles/portal/customer-pages.css                                       # new file from this change
for f in dashboard portal-modern storefront; do cmp portal/static/portal/$f.css staticfiles/portal/$f.css && echo "$f.css restored"; done
sudo systemctl restart cloud-portal && systemctl is-active cloud-portal
curl -s $B/plans/ | grep -c 'customer-pages.css'      # 0 after rollback
ls -d billing monitoring-ca
```

If a `cmp` fails, run `manage.py collectstatic --noinput` once more and re-compare. `git reset --hard` is safe here only because step 0 showed no tracked changes; the previous commit also remains in `git reflog`.

After a successful deploy keep `~/deploy-records/` for at least a week.
