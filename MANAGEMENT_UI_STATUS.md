# Management UI refinement status — ICT Ventures Cloud Portal

Last updated: 2026-10-15 (after Batch 4 — all planned batches complete, pending your final review).

## Baseline and branch
- Baseline branch: `design/management-ui`, exact commit `38283446b603dd91c66574ab13503da31c32ff5e`.
- Working branch: `design/management-refinement`, created from that exact commit.
- Nothing merged or deployed. Only the working branch is pushed.

## Scope rules (from the brief)
- Allowed: `portal/templates/management/`, `portal/static/portal/management.css`, this file.
- Not allowed: Python, settings, models, migrations, auth, permissions, sessions, payments, provisioning, `templates/admin/base_site.html`, frameworks, deployment.
- Real data only: no invented revenue charts or server-health metrics. Financial/service lifecycle records stay read-only. The confirmed reconciliation workflow is unchanged and no operational actions are added.
- No AI branding or co-author trailers in commits.

## Design decisions
- Same blue/navy palette as the customer portal. Tokens are `--m-*` custom properties on `body.management-ui` (navy `#14213d`, primary `#2563eb`, soft `#eff6ff`, lines `#e2e8f0`).
- Header is sticky on desktop; breadcrumbs sit on a white bar under it.
- Sidebar is 248px navy, sticky, full height, with grouped sections (Workspace, Team, Records) and line icons.
  Icons are decorative CSS masks keyed on a `data-area` attribute, so no new images or frameworks are loaded.
- Navigation only lists what Django's permission-filtered `available_apps` and existing `can_view_services` allow. Conditions are unchanged.
- Tablet/phone (<=900px): sidebar becomes a navigation strip above the content. At <=600px it is a single horizontally scrolling row with a fade at the right edge.
- Overview: stat cards (icon, label, count, link), "Record areas" list with icon rows and the existing add links styled as small buttons,
  and "Your recent actions" with action type (Added/Changed/Deleted), record type and a formatted timestamp. All from the existing `cards`, `app_list`, `recent_actions` context.
- Display-only label fix: "VPSPlan" now reads "VPS plans" / "VPS plan" in the sidebar, record list and activity (Django's default capitalised "Vps plans").
- Lists (Batch 2): every Django changelist and the VPS services page share one card: toolbar (search or filter bar), table, footer.
  Changelists are styled with CSS only (Django's `change_list.html` is not overridden, so the legacy admin is unaffected).
  Table headers are small uppercase labels, rows have a quiet hover, the first column stays visible while scrolling sideways (not on phones).
  Pagination uses page buttons with the current page filled blue. Filters are a right-hand column on desktop and wrapped chips above the list at <=900px.
- "Add ..." is the one filled button on a list page. Other object tools (History, Reconcile provisioning status) are outlined so the remote workflow is not emphasised.
- Services page: visible labels for the existing `q` and `status` fields, Search and Clear, status pills (Active, Provisioning, Paid, Pending, Failed, Cancelled), Previous/Next as buttons with the same filter-preserving URLs.
- Forms and record details (Batch 3): fieldsets are cards with a quiet heading; each row is label on the left, control and help on the right (stacked on tablet/phone).
  Read-only records (orders, invoices, payments, subscriptions, customers) show as label/value pairs; the order record uses two columns from 1200px.
  The save bar is one row of buttons (Save filled, others outlined, Delete red where Django offers it) and is sticky at the bottom of the window on tablet/desktop forms that can be saved.
  Errors: red summary note, red label and outlined field, message above the control. Messages (success/warning/error) are tinted bars.
  The permission selector (Django SelectFilter2) keeps its markup and scripts; only headings, borders, list height and buttons are restyled.
  The reconcile page is a single confirmation card; wording, POST form and CSRF token are unchanged.
- Staff login (Batch 4): one centred card on the page background with the brand mark, a "Staff sign in" heading (CSS-generated text, because the login template cannot be overridden without Python changes),
  labelled fields, a full-width filled "Log in" button, and the error note in the same red style as forms. Django's login form, field names, CSRF token and autofocus are untouched.

## Changed files (Batch 1)
- `portal/templates/management/navigation.html`: group wrappers, `data-area` hook, "VPS plans" label. Links, URL names, `aria-label`s, `aria-current` logic and permission conditions kept.
- `portal/templates/management/index.html`: icons, card/list/activity markup, activity kind line. Same context variables, URLs and empty states (including the "No record permissions assigned" text).
- `portal/static/portal/management.css`: new tokens, header, breadcrumbs, sidebar, icons, overview and responsive rules.
- `MANAGEMENT_UI_STATUS.md`: this file.

## Changed files (Batch 2)
- `portal/static/portal/management.css`: consolidated list block (object tools, card, toolbar, tables, status pills, footer/pagination, filters) and tablet/phone list rules. Old list and services rules were replaced.
- `portal/templates/management/services.html`: restructured markup into the shared list card. Field names/IDs, GET method, table values, pagination URLs, empty-state text and conditions unchanged. Adds `management-services` body class.
- `MANAGEMENT_UI_STATUS.md`.

## Changed files (Batch 3)
- `portal/static/portal/management.css`: forms/record-detail block, error and message styles, save bar, permission selector, reconcile card, phone overrides for Django's fixed-width form rule.
- `portal/templates/management/sync.html`: confirmation card markup only (same text, form method, CSRF token, URLs).
- `MANAGEMENT_UI_STATUS.md`.
- Provenance note: at the start of Batch 3 the working tree already held uncommitted edits to these two files that were not made in the Batch 2 conversation. They were reviewed line by line, found to be presentation-only and in scope, then verified and completed (phone width fix, error colours) before commit.

## Changed files (Batch 4)
- `portal/static/portal/management.css`: login rules rewritten. No template changed in this batch.
- `MANAGEMENT_UI_STATUS.md`.

## Checks actually run (Batch 1)
Environment: Django 6.1.1 from `requirements.txt` in a throwaway venv, DEBUG-mode SQLite (in-memory test database), placeholder SECRET_KEY,
all provisioning/payment/Hestia variables set empty. No `.env`, no credentials, no external calls.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes.
- Full Django suite: **192 tests passed** (same as baseline). Run before the change and again after it.
- `node --test portal/test_provisioning_poll.cjs`: **9 passed**.
- Browser render (Chromium headless, requests restricted to the local server, disposable SQLite with synthetic data created only outside the repo):
  Overview as administrator, billing-only staff (invoice/payment/subscription view) and no-permission staff, each at 1440, 1024, 768 and 390px.
  All returned HTTP 200, no horizontal page overflow, no console or page errors. Screenshots were inspected by eye.
  Orders list, order detail, services, staff list and plan add page also load inside the new shell at the same four widths (200, no overflow); their tables, filters and forms are not restyled yet.
- Restricted staff see only their own links in the sidebar, cards and record list (checked visually for the billing-only account; the existing test `test_limited_staff_navigation_exposes_only_allowed_record_areas` still passes).

## Checks actually run (Batch 2)
Same environment as Batch 1 (throwaway venv, DEBUG SQLite, integrations empty, synthetic data outside the repo; 52 orders to exercise pagination).
- `manage.py check` clean; `makemigrations --check` no changes; full Django suite **192 passed**; `node --test portal/test_provisioning_poll.cjs` **9 passed**.
- Rendered at 1440/1024/768/390px as administrator: services, orders, customers, invoices, payments, subscriptions, VPS plans, staff accounts. All 200, no horizontal page overflow, no console errors. Screenshots inspected by eye.
- Restricted accounts: billing-only and operations-only staff got 403 on pages outside their permissions (expected; permissions unchanged).
- Interaction check in Chromium: services search + status filter, Next/Previous keep `q`, `status` and `page`; Clear resets; changelist search and a filter link work; the Reconcile link still shows on order detail for an account with order change permission.

## Checks actually run (Batch 3)
Same environment as Batch 1 and 2 (throwaway venv, DEBUG SQLite, integrations empty, synthetic data outside the repo).
- `manage.py check` clean; `makemigrations --check` no changes; full Django suite **192 passed**; `node --test portal/test_provisioning_poll.cjs` **9 passed**.
- Rendered at 1440/1024/768/390px as administrator: order detail, reconcile page, invoice detail, customer detail, plan change, plan add, staff add, staff edit (with permission selector), password change. All 200, no page overflow, no console errors. Screenshots inspected by eye.
- Real-scroll check of the sticky save bar on the staff edit page (1440x760): bar stays at the bottom while scrolling and settles below the last card at the end.
- Validation error (plan with CPU 0 and a negative price) and save success (plan description edit on the disposable database) states were rendered and inspected. The error summary, red label/outline and success message display correctly.
- Fixed during the batch: Django's phone rule `.aligned .form-row > div { width: calc(100vw - 30px) }` made fields overflow and clip on phones; overridden. Error list inherited a grey background and error colours lost a specificity tie; fixed.
- Not exercised: a POST to the reconcile page (it contacts the provisioner path; existing tests cover it with the provisioner mocked), staff creation, or permission edits in the browser.

## Checks actually run (Batch 4, final pass)
Same environment as earlier batches.
- `manage.py check` clean; `makemigrations --check` no changes; full Django suite **192 passed**; `node --test portal/test_provisioning_poll.cjs` **9 passed**.
- Login page rendered at 1440/1024/768/390px, plus the wrong-password error state at 1440 and 390px. No overflow.
- Final sweep: 18 Management pages x 4 widths as administrator (72 renders) and the overview for billing-only and operations-only staff: all HTTP 200, zero horizontal overflow, zero console or page errors.
- Automated accessibility (axe-core 4.10.2, WCAG 2 A/AA and 2.1 A/AA tags) on login, 18 pages as administrator, and the overview for three restricted accounts, at 1440 and 390px:
  no violations except one rule on the staff-edit page, `aria-prohibited-attr` (2 elements) from Django's own SelectFilter2 search tooltip icon.
  This is the same finding already documented in `deploy/MANAGEMENT_UI.md`; it is not new markup and was left alone rather than changing Django's permission widget.
  Automated checks are not a real screen-reader test and do not prove accessibility compliance.
- Keyboard Tab walkthrough (Chromium) on overview, services, orders list, order detail, plan add and staff edit at 1440 and 390px: "Skip to main content" is the first stop, every stop showed a visible focus ring, focus reached the main content and left the page at the end (no trap).
  Only Tab order and focus visibility were checked, not screen-reader announcements or switch/voice control.
- Scope check against the baseline: only `portal/templates/management/*`, `portal/static/portal/management.css` and this file differ. No Python, settings, models, migrations, auth, permissions, sessions, payments or provisioning file changed, and `templates/admin/base_site.html` is unchanged.
- Legacy admin (`/admin/`) and customer pages (`/`, `/accounts/login/`) load no `management.css` and no Management body class (browser check plus the existing boundary test).

## Known issues and unverified
- Not run: real screen reader or other assistive technology, Safari/Firefox, real PostgreSQL, live provisioning or payment behaviour. The reconcile POST was not submitted in the browser (existing tests cover it with the provisioner mocked).
- `deploy/MANAGEMENT_UI.md` was not edited (outside the stated scope). It still describes the first Management design (192 tests, earlier checks); update it only if you want it to match this branch.
- The stylesheet link in `templates/admin/base_site.html` still uses `?v=management-1`. That file is out of scope, so browsers that cached the old CSS may need a hard refresh until the query string is bumped (needs your OK to touch that file).
- Sidebar and fade on phones were checked at 390px only; very narrow (<360px) widths are untested.
- Dark mode is not supported by the Management theme (unchanged from baseline).
- The "Staff sign in" heading on the login page is CSS-generated text, so it is not in the page's accessibility tree; the page already has the brand link and labelled fields. Making it a real heading needs a login template (a Python change to point the site at it), which is out of scope.
- Django generates some list wording from model names (page titles such as "Select vps plan to change", button "Add vps plan", "Add user" on Staff accounts). Changing it needs Python or model changes, so it is left as is. The overview and sidebar already say "VPS plans".
- Status columns in Django changelists (orders, invoices, payments) are plain text, not pills, because badges would need Python or a changelist template override that would also affect the legacy admin. Pills exist on the services page.
- The Django 403 page shown to staff who open a page outside their permissions is not themed (outside this scope).
- Filter groups on tablet/phone are always expanded (Django's `details` elements are fixed open), so on lists with many filters the table starts lower.

## Latest saved work and exact next step
- Latest saved code commits on `design/management-refinement`: Batch 1 `dfb210a08633e609b050aa32d9cb7c2be1033794` (shell, sidebar, overview); Batch 2 `74996fe` (lists and services); Batch 3 `283e9d6` (forms, record details, reconcile page); Batch 4 `e065240` (login, final pass). Commits whose message starts "Record" only update this file.
- Batches 1-3 were approved. All four planned batches are now saved. Next step: your visual review of Batch 4 (login and final pass) and a preview on the isolated test environment with integrations disabled, checking an administrator and restricted staff separately.
  After that, merge and deployment are separate decisions for you; neither has been done. Optional follow-ups if wanted: bump the `?v=management-1` stylesheet query in `templates/admin/base_site.html` (needs approval to touch that file), and update `deploy/MANAGEMENT_UI.md`.
