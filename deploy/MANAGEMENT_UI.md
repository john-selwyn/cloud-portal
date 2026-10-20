# Management workspace design

Prepared 15 October 2026 on `design/management-ui`, based on the deployed customer
redesign and staff-account integration at `b899140`. Refined 15–16 October 2026 on
`design/management-refinement`, created from `design/management-ui` commit
`38283446b603dd91c66574ab13503da31c32ff5e`. `MANAGEMENT_UI_STATUS.md` in the
repository root records the batch history, decisions and checks in more detail.

## Scope

This change presents the existing `/management/` functionality as a polished blue/navy
staff workspace. It adds a permission-filtered sidebar, an overview built from existing
record counts and the signed-in member's own recorded actions, styled lists, filters,
record details and forms, service status badges, and a matching staff login. The counts
come from the existing permitted querysets; there are no invented infrastructure
metrics or revenue charts.

The refinement is presentation only. The existing AdminSite, ModelAdmins, URLs,
permissions, CSRF, staff cookies, search/filter/pagination, staff creation, validation,
and audit behavior remain authoritative. Financial and service lifecycle records
(orders, invoices, payments, subscriptions) remain read-only. Existing confirmed status
reconciliation remains the only Management remote workflow; no new power, payment,
provisioning, deletion, refund or suspension action is introduced.

### Who can change what (unchanged by this work)

- Orders, invoices, payments and subscriptions: view only; no add, change or delete.
- Customers: staff who hold the customer change permission can edit contact details
  (full name, company, phone). Ownership stays fixed: the linked login account, the
  account type and the created date are read-only for everyone. Customer records cannot
  be added or deleted from Management. Staff with view permission only see every field
  as read-only.
- Plans: staff with the plan permissions can add and edit plans. Name and resources
  become read-only once an order uses the plan. Plans cannot be deleted.
- Staff accounts: administrators only; no deletion; administrator accounts are not
  editable here.

## Design

- Same blue/navy palette as the customer portal, defined as `--m-*` tokens on
  `body.management-ui`.
- Sidebar: grouped sections (Workspace, Team, Records) with decorative line icons.
  It lists only what Django's permission-filtered `available_apps` and the existing
  service-access flag allow. Staff-account links remain administrator-only.
- Tablet and phone: the sidebar becomes a navigation strip above the content; on phones
  it is one horizontally scrolling row.
- Lists share one card (toolbar, table, footer). Filters are a right-hand column on
  desktop and wrapped chips above the list at 900px and below. The first table column
  stays visible while scrolling sideways on tablet and desktop.
- Forms and record details: label/control rows, read-only values as label/value pairs,
  a sticky save bar, red error styling, tinted success/warning/error messages, and a
  restyled (not replaced) permission selector.
- The VPS services page and reconcile confirmation use the same card style. The
  reconcile wording, POST form and CSRF token are unchanged.
- Staff login: one centred card using Django's own form.

## Implementation

- `templates/admin/base_site.html` extends the bundled template of the same name.
  Django skips the current origin when resolving the parent, preventing recursion.
  Overrides are conditional on `management_ui`; the legacy admin falls back to its
  bundled presentation. Customer templates do not use this base. The Management
  stylesheet link carries the cache-busting query `?v=management-2` (raised from
  `management-1` so browsers fetch the refined stylesheet); it remains inside the
  `management_ui` condition.
- `cloud_portal/settings.py` adds `BASE_DIR / 'templates'` to the template search
  directories (from the earlier Management work). Other deployment and database
  settings are unchanged.
- `ManagementSite.each_context` supplies the presentation-only `management_ui` flag.
  No queryset or permission logic changed.
- `portal/static/portal/management.css` scopes styling to `.management-ui`.
- Templates changed in `portal/templates/management/`: `navigation.html`, `index.html`,
  `services.html`, `sync.html`. Django's own changelist, form and login templates are
  used as they are and are styled with CSS only.
- Service search field names, GET behavior, table values and pagination links remain
  intact. The services table wrapper keeps its accessible region label and keyboard
  focus for scrolling.
- Files changed by the refinement: `portal/static/portal/management.css`, the four
  templates above, the cache-busting query in `templates/admin/base_site.html` (the only
  change to that file), this document and `MANAGEMENT_UI_STATUS.md`. No Python,
  settings, model, migration, authentication, permission, session, payment or
  provisioning file changed.

## Validation

Local execution used Django 6.1.1 from `requirements.txt` in a throwaway environment,
with a temporary SQLite database, a placeholder secret key, and every provisioning,
payment and hosting-panel variable empty. No production `.env`, credentials or
external provider were used. Browser checks used headless Chromium restricted to the
local test server and synthetic local data that is not part of the application or
deployment.

- Full Django suite: **192 passed** (the same count as the baseline; no tests were added
  or removed by the refinement). System checks passed; no model migration changes
  detected.
- `node --test portal/test_provisioning_poll.cjs`: **9 passed**.
- Rendering: 18 Management pages at 1440, 1024, 768 and 390px as an administrator
  (72 renders): overview, VPS services, orders list and detail, reconcile page,
  customers list and detail, invoices list and detail, payments, subscriptions, plans
  list, change and add, staff list, add and edit, and password change. The overview was
  also rendered for a billing-only and an operations-only staff account. Every one of
  those renders returned HTTP 200 with no horizontal page overflow and no console or page
  errors; screenshots were inspected by eye. The login page was rendered at all four
  widths (no horizontal overflow) and its wrong-password state at 1440 and 390px;
  console errors were not separately recorded for the login page.
- Interaction checks in Chromium: services search, status filter, Next/Previous and Clear
  keep the filter values; changelist search and filter links work; the sticky save bar
  stays in view while scrolling; a plan validation error and a successful plan edit
  display correctly (on the disposable database only).
- Customer editing (verified against a disposable database): a staff account with
  customer change permission could save full name, company and phone; a posted attempt
  to change the owner was ignored; a view-only account saw read-only fields and its save
  attempt was refused (403); adding or deleting a customer was refused (403).
- Boundaries: restricted staff received 403 for pages outside their permissions; the
  legacy admin and customer pages load no Management stylesheet or body class.
- Automated accessibility (axe-core 4.10.2, WCAG 2 A/AA and 2.1 A/AA rules) on the login
  page, the 18 administrator pages and the three restricted-account overviews at 1440
  and 390px: no violations except one rule on the staff edit page,
  `aria-prohibited-attr` (2 elements), generated by Django's bundled permission selector
  search-tooltip icon. It is not new application markup and the framework widget was
  left unchanged.
- Keyboard walkthrough (Tab) on the overview, services, orders list, order detail, plan
  add and staff edit pages at 1440 and 390px: "Skip to main content" was the first stop
  on every page except the plan form (its name field has focus on load, so the first Tab
  moved to the next field); every stop showed a visible focus ring, focus reached the
  main content, and focus left the page at the end (no trap). On the login page the
  username field has focus on load and the first Tab moved to the password field.

These automated checks are not a real screen-reader test and do not establish full
accessibility compliance.

### Not verified

Real assistive-technology use, other browsers (only Chromium was used), live PostgreSQL
behavior, live infrastructure or payment behavior, and submitting the reconcile form
in a browser (the existing tests cover that path with the provisioner mocked). None of
the live actions are needed to review this presentation change.

## Visual approval

On 16 October 2026 the repository owner reviewed the final preview and approved its
appearance. This is a visual approval limited to what the owner reviewed. It is not an
approval of functionality, security, permissions, accessibility, other browsers,
database behavior or deployment, and it does not authorize a merge, deployment or
restart.

## Preview checklist

Use the existing isolated preview, with its test database and integration credentials
disabled. Check administrator and restricted-staff views separately.

1. Sign in at `/management/login/`; try a wrong password; check tablet and phone widths.
2. As an administrator, confirm the sidebar, overview cards and record areas.
3. As restricted staff, confirm the sidebar, cards and record list show only that
   account's areas, and that pages outside it are refused.
4. Open orders, invoices, payments and subscriptions: every field is read-only and there
   is no add or delete control. Customers: staff with change permission can edit name,
   company and phone; the login account, account type and created date are read-only;
   there is no add or delete control.
5. Plans: add a plan with invalid values to see the errors, then edit a plan. Staff
   accounts: add and edit, and check the permission selector.
6. VPS services: search, filter, paginate and clear. Order detail: confirm the
   reconcile link appears only for accounts with order change permission.
7. Open the customer portal and `/admin/` and confirm they look as before.
8. Hard-refresh once to confirm the stylesheet loads with `?v=management-2`.

Retain both access and form validation checks; appearance does not grant access.

## Preview and deployment boundary

Nothing in this task is deployed. A future deployment requires the template directory,
the updated stylesheet and base template, static collection, Django checks and the usual
separately authorized service restart. No model or schema migration is introduced. A
code rollback to the preceding compatible deployment needs no database reversal;
recorded business and staff edits (including customer contact edits) must be retained.
This document is not authorization to deploy or restart.
