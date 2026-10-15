# Management UI refinement status — ICT Ventures Cloud Portal

Last updated: 2026-10-15 (after Batch 2).

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
- Rules for sections not yet reworked (record details, forms, login) are carried over unchanged from the baseline, apart from the shell.

## Changed files (Batch 1)
- `portal/templates/management/navigation.html`: group wrappers, `data-area` hook, "VPS plans" label. Links, URL names, `aria-label`s, `aria-current` logic and permission conditions kept.
- `portal/templates/management/index.html`: icons, card/list/activity markup, activity kind line. Same context variables, URLs and empty states (including the "No record permissions assigned" text).
- `portal/static/portal/management.css`: new tokens, header, breadcrumbs, sidebar, icons, overview and responsive rules.
- `MANAGEMENT_UI_STATUS.md`: this file.

## Changed files (Batch 2)
- `portal/static/portal/management.css`: consolidated list block (object tools, card, toolbar, tables, status pills, footer/pagination, filters) and tablet/phone list rules. Old list and services rules were replaced.
- `portal/templates/management/services.html`: restructured markup into the shared list card. Field names/IDs, GET method, table values, pagination URLs, empty-state text and conditions unchanged. Adds `management-services` body class.
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

## Known issues and unverified
- Not run: axe/contrast checks, keyboard-only walkthrough, real screen reader, Safari/Firefox, real PostgreSQL. Automated checks are not a screen-reader test.
- The stylesheet link in `templates/admin/base_site.html` still uses `?v=management-1`. That file is out of scope, so browsers that cached the old CSS may need a hard refresh until the query string is bumped (needs your OK to touch that file).
- Sidebar and fade on phones were checked at 390px only; very narrow (<360px) widths are untested.
- Dark mode is not supported by the Management theme (unchanged from baseline).
- Record details, forms and login are still in baseline styling (Batches 3 and 4).
- Django generates some list wording from model names (page titles such as "Select vps plan to change", button "Add vps plan", "Add user" on Staff accounts). Changing it needs Python or model changes, so it is left as is. The overview and sidebar already say "VPS plans".
- Status columns in Django changelists (orders, invoices, payments) are plain text, not pills, because badges would need Python or a changelist template override that would also affect the legacy admin. Pills exist on the services page.
- The Django 403 page shown to staff who open a page outside their permissions is not themed (outside this scope).
- Filter groups on tablet/phone are always expanded (Django's `details` elements are fixed open), so on lists with many filters the table starts lower.

## Latest saved work and exact next step
- Latest saved code commits on `design/management-refinement`: Batch 1 `dfb210a08633e609b050aa32d9cb7c2be1033794` (shell, sidebar, overview); Batch 2 `74996fe` (lists and services). Commits whose message starts "Record" only update this file.
- Batch 1 was approved. Next step: wait for the visual review of Batch 2. If approved, Batch 3: record details and forms (order detail with its read-only fields, plan add/change, staff add/edit with the permission selector, password change, reconcile page `sync.html`, `order.html`). Then Batch 4: staff login and final pass (axe, keyboard checks, `deploy/MANAGEMENT_UI.md` note).
