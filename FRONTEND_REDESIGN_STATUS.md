# Frontend redesign status — ICT Ventures Cloud Portal

Last updated: 2026-10-12. Keep this file free of passwords, tokens, keys and customer data.

## Branches and commits
- Source branch: `codex/windows-rdp`, verified commit `738156c7c4246908d0f9756cb482ed3d5ca70289`.
- Redesign branch: `design/portal-redesign` (created from the source commit).
- Latest saved commit: local commit "Improve portal navigation and page styling" on `design/portal-redesign` (not pushed; see Save state).
- The repository's default branch was not used or assumed to match the deployed site.

## Scope rules (from the project brief)
- Allowed: `portal/templates/portal/`, `portal/templates/registration/login.html`, `portal/static/portal/`, this file.
- Not allowed: Python, settings, models, migrations, `.env`, APIs, auth, payments, provisioning logic, JS business behavior, framework changes, deployment.
- Stay a Django-template site. No fake data, no do-nothing buttons, no staff/admin links for customers.

## Agreed design system (v1)
Direction: calm, flat and readable. Keep the ICT Ventures navy + teal identity from the storefront. Remove gradients, blur, hover-lift and decorative shapes. Keep only functional motion (progress bar, spinner), and respect reduced motion.

Tokens live at the top of `portal/static/portal/portal.css` (`:root`):
- Surfaces: `--bg #f5f8f8`, `--surface #fff`, `--surface-alt #f1f6f6`, `--line #d9e3e2`.
- Text: `--ink #1a2835`, `--muted #56656f` (about 5.6:1 on bg).
- Primary: `--primary #007b76` (white on it 5.13:1), `--primary-hover #00625e`, `--primary-soft #e1f3f0`, `--primary-line #a5c9c6`, `--link #006d69`.
- Dark sections: `--navy #19222b`, `--navy-raised #212d37`, `--on-navy #c9d6d8`, `--on-navy-muted #aebfc2`, `--accent-on-navy #8de2d8`.
- Status: success/warning/danger text + background pairs (badge colours unchanged in value).
- Form control border `--control-border #6c7d89` (4.3:1 on white, meets 3:1 for controls).
- Focus ring `--focus #007b76`, 3px, offset 3px (light ring on navy sections).
- Radius: `--radius 12px` (cards), `--radius-sm 8px` (controls). Hero 16px.
- Spacing scale: `--space-1..8` = .25, .5, .75, 1, 1.5, 2, 3, 4.5 rem. Content width `--content-width 1240px` (header and page content now share it).
- Type: Inter / Segoe UI / system-ui stack (no web font loaded), 16px base, 1.6 line height, heading tracking -.02em, h1 `clamp(1.85rem, 3vw, 2.3rem)`.
- Components so far: header + nav (`.main-nav`), buttons (`.button`, `.button.secondary`, `.button.small`), cards, notices, form controls, tables, badges, footer, pagination, storefront hero/sections/FAQ/banner.

CSS load order (unchanged): `portal.css` (tokens + page components + JS-state classes) → `portal-modern.css` (shared shell/controls) → `storefront.css` (public pages). All three links in `base.html` carry `?v=redesign-1` for cache busting.

## Completed — Batch 1 (shared layout, homepage, CSS)
Changed files:
- `portal/templates/portal/base.html`: added `class="main-nav"` to header nav, `aria-current="page"` on the active link, cache-bust query on all three stylesheets. No URL names, blocks, forms, CSRF token or conditions changed.
- `portal/templates/portal/home.html`: decorative "01—02" label removed; panel label is now an `h2.panel-title`; decorative numerals (`.route-index`, `.choice-icon`, `.step-number`) marked `aria-hidden`. Copy, links and URL names unchanged.
- `portal/static/portal/portal.css`: tokens added; hard-coded blue replaced with tokens; header-nav rules re-scoped from bare `nav` to `.main-nav`; pagination `nav.pagination` given its own rules; denser table cells; skip link and focus ring improved. Selector names used by JavaScript untouched.
- `portal/static/portal/portal-modern.css`: rewritten as the shared shell layer (header, nav, buttons, forms, tables, badges, footer). Removed unused legacy classes (`.hero*`, `.terminal*`, `.feature-*`, `.hero-points`) after confirming no template references them.
- `portal/static/portal/storefront.css`: same class names, flat styling, tokens, calmer spacing; hero gradient/ring/blur and hover-lift removed.

## Dependencies that must be preserved
Inline JS lives in three templates (not yet touched):
- `provisioning_status.html`: IDs `provisioning-status`, `provisioning-step`, `provisioning-percent`, `provisioning-bar`, `provisioning-vmid`, `provisioning-ip`, `setup-vps-state`, `setup-access-state`, `access-wait-status`, `access-wait-message`, `access-wait-elapsed`, `access-next-check`; `data-status-url`, `data-order-id`, `data-initial-status`, `data-operating-system`, `data-initial-ip`, `data-initial-access`. JS sets classes `setup-stage` + `complete`/`working`, `.provisioning-bar.complete`, `.provisioning-failed`, and uses the `hidden` attribute on `#access-wait-status`.
- `vps_detail.html`: IDs `windows-access-form`, `windows-password-box`, `windows-password`, `reveal-windows-password`, `windows-access-message`, `hide-windows-password`, `copy-windows-password`, `runtime-state`, `power-help`; attributes `data-copy`, `data-confirm` (on power forms), `data-power="start|shutdown|reboot"`; JS sets `runtime-state <state>` classes (`running`, `stopped`, `paused`, `suspended`, `unknown`, `checking`) and enables/disables `.power-button`.
- `select_plan.html`: IDs `id_operating_system`, `id_ssh_public_key`, `access-help`; JS uses `closest('p')` and `hidden` on the SSH key field's paragraph, so keep Django's `form.as_p` structure.
- Global: `.nav-button` (logout button), `.badge` + status class (`pending`, `overdue`, `active`, `paid`, `failed`, `cancelled`, `provisioning`).

## Checks performed (actual results)
- Cloned `codex/windows-rdp` and confirmed HEAD `738156c`. Inspected base, home, all three CSS files, login, pagination, and every `<script>`, ID and `data-` attribute in the templates.
- CSS brace balance: OK for all three files.
- CSS selector comparison before/after: only bare `nav`, `nav a`, `nav form` replaced by `.main-nav` equivalents; unused legacy classes removed; every JS-driven class (`.setup-stage.*`, `.runtime-state.*`, `.provisioning-bar.complete`, `.provisioning-failed`, `.access-wait-status[hidden]`, `.power-button:disabled`, `.copy-button`, `.connection-box`, `.access-spinner`) still present in `portal.css`.
- Django tags in `base.html` and `home.html` (URL names, blocks, CSRF token, load) hashed identical before/after.
- Rendered `base.html` + `home.html` through Django (stub URL config) as signed-out and signed-in: renders without errors; signed-out nav has 4 links, signed-in 7 including a Logout form with a CSRF token; `aria-current` appears on the right link; no admin/staff links in the output.
- Contrast ratios calculated for the new palette (all text pairs listed above are at least 4.5:1; controls at least 3:1). The previous primary button (white on #009d97) was 3.35:1 and the old footer text 3.4:1, so these were fixed.
- Templates other than `base.html` and `home.html` have zero diff.

## Not yet checked (needs a real browser or the running site)
- No screenshots or visual review were possible (browser download is blocked in the working environment). The homepage and header have not been seen rendered at desktop, tablet or phone widths.
- Pages other than the homepage inherit the new colours, spacing and header but have not been reviewed: dashboard, my_vps, vps_detail, provisioning_status, plans, select_plan, review_order, orders, order_detail, invoices, invoice, account, register, login, payment_return, checkout_error, web_hosting.
- Keyboard tab order and focus visibility, and a screen-reader pass, still to be run.
- The Django project's own test suite and `manage.py check` were not run (no `.env`/database available here).
- Pagination (`nav.pagination`) was re-styled but not viewed.

## Known problems / risks
- The bare `.active`, `.pending`, `.paid`, `.failed` classes in `portal.css` style any element with those class names, not only `.badge`. Nav links use `.active` and are overridden by `.main-nav a.active`; left as is for now.
- `.nav-wrap` and `.container` now share one width (1240px); previously 1200px vs 1240px.
- Dashboard "stat" cards lost the decorative circle; other pages' layouts are otherwise unchanged and unreviewed.

## Current task and exact next step
Batch 1 is complete pending your visual review. Next:
1. Deploy nowhere. Run the site locally (or on a staging copy) from branch `design/portal-redesign` and send screenshots of: homepage, login, dashboard, VPS plans, My VPS, VPS detail, provisioning status.
2. Batch 2: `registration/login.html`, `register.html`, `account.html` (auth and form styling, error lists, labels).
3. Batch 3: `dashboard.html`, `my_vps.html` (server cards, status badges).
4. Batch 4: `vps_detail.html` (connection boxes, password reveal, power controls, confirmations) and `provisioning_status.html`. Re-check every ID/class listed above before editing.
5. Batch 5: plans, select_plan, review_order, orders, order_detail, invoices, invoice, payment pages, web_hosting.

## Save state
- Saved to local branch `design/portal-redesign` in the working copy (commit recorded below).
- This commit exists only in the working copy used for this session; pushing to GitHub was not possible from there (no write access to the repository). Nothing is on GitHub yet. Apply the patch file or copy the changed files into your own clone, then commit and push yourself.
- Commit hash: run `git log -1 --format=%H design/portal-redesign` (a commit cannot contain its own hash). Message: "Improve portal navigation and page styling".
