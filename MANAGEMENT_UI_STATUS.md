# Management UI refinement status — ICT Ventures Cloud Portal

Last updated: 2026-10-15 (after Batch 1).

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
- Rules for sections not yet reworked (tables, filters, forms, login) are carried over unchanged from the baseline, apart from the shell.

## Changed files (Batch 1)
- `portal/templates/management/navigation.html`: group wrappers, `data-area` hook, "VPS plans" label. Links, URL names, `aria-label`s, `aria-current` logic and permission conditions kept.
- `portal/templates/management/index.html`: icons, card/list/activity markup, activity kind line. Same context variables, URLs and empty states (including the "No record permissions assigned" text).
- `portal/static/portal/management.css`: new tokens, header, breadcrumbs, sidebar, icons, overview and responsive rules.
- `MANAGEMENT_UI_STATUS.md`: this file.

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

## Known issues and unverified
- Not run: axe/contrast checks, keyboard-only walkthrough, real screen reader, Safari/Firefox, real PostgreSQL. Automated checks are not a screen-reader test.
- The stylesheet link in `templates/admin/base_site.html` still uses `?v=management-1`. That file is out of scope, so browsers that cached the old CSS may need a hard refresh until the query string is bumped (needs your OK to touch that file).
- Sidebar and fade on phones were checked at 390px only; very narrow (<360px) widths are untested.
- Dark mode is not supported by the Management theme (unchanged from baseline).
- Tables, filters, record details, forms and login are still in baseline styling. Batch 2 onward.

## Latest saved work and exact next step
- Latest saved commit: see `git log -1` on `design/management-refinement` (Batch 1 shell, sidebar, overview).
- Next step: wait for the visual review of Batch 1. If approved, Batch 2: changelist tables, search/filter panel, pagination and the VPS services page
  (`management.css`, `services.html`). Then Batch 3: record details and forms (including order detail and the reconcile page). Then Batch 4: staff login and final pass (axe, keyboard checks, docs update).
