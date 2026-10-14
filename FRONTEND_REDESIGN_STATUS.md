# Frontend redesign status — ICT Ventures Cloud Portal

Last updated: 2026-10-14 (Batch 5).

## Branches and commits
- Source branch: `codex/windows-rdp`, verified commit `738156c7c4246908d0f9756cb482ed3d5ca70289`.
- Redesign branch: `design/portal-redesign` (created from the source commit).
- Latest saved commit: see "Save state" at the bottom.
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

### Batch 1 visual approval
- On 2026-10-13 the project owner previewed the Batch 1 changes through an SSH tunnel and reported being happy with the appearance they reviewed.
- This is a visual approval only, limited to what the owner looked at. It does not mean every page was reviewed, and no functional testing by the owner was reported.

## Completed — Batch 2 (login, registration, account)
Changed files:
- `portal/templates/registration/login.html`: form gets `class="auth-form"`, submit button gets `type="submit"` and `class="wide"`, "Create an account" line gets `class="auth-switch"`.
- `portal/templates/portal/register.html`: same pattern as login.
- `portal/templates/portal/account.html`: heading wrapped in the existing `.page-heading` pattern; layout gets `account-layout`, profile form `account-form`, submit button `type="submit"`, sign-in details aside labelled by its heading (`aria-labelledby="signin-details"`).
- `portal/static/portal/portal-modern.css`: new "Auth and account pages" section (card width and padding, label/help-text/password-rule spacing, invalid-field highlight via `[aria-invalid="true"]`, full-width submit button, mobile padding).

Kept exactly as before: `{{ form.as_p }}` rendering, field names, labels, help text, validation messages (all produced by the existing Django forms), `{% csrf_token %}`, the hidden `next` field on login, form methods, form actions (none; forms post to their own URL), and all URL names. No JavaScript is used on these pages.
Deliberately not added: forgot-password/reset links (no reset templates or email setup in this project) and any "change email/username" controls (the account form only edits full name, company and phone).

### Batch 2 visual approval
- On 2026-10-13 the project owner reviewed the Batch 2 preview and reported being happy with its appearance.
- This is a visual approval only, limited to what the owner looked at. No other checks (functional, keyboard, screen reader, every viewport or error state) were reported by the owner.

## Completed — Batch 3 (dashboard, My VPS)
Changed files:
- `portal/templates/portal/dashboard.html`: summary cards get `stat-card` / `stat-label` / `stat-value` / `stat-link` classes and the group is a labelled list; server cards get a status class (`server-card-<status>`); provisioning track gets `role="progressbar"` with `aria-valuenow` from the same `order.provisioning_progress` variable; "Manage VPS" is wrapped in the existing `.server-card-actions`; the empty-state link to the plans page is now a small button (the trailing arrow was dropped from its text).
- `portal/templates/portal/my_vps.html`: server cards get the status class; provisioning track gets the same progressbar attributes.
- `portal/static/portal/portal-modern.css`: new "Dashboard and VPS lists" section (equal-height summary cards, IP shown on its own row with vCPU/RAM/storage below, thicker accent edge on provisioning (primary) and failed (danger) cards, dashed empty-state cards, compact summary rows on phones, full-width primary button on small screens). `.badge.cancelled` and `.badge.void` are now neutral grey instead of red; failed stays red.

Kept exactly as before: every Django variable, condition, loop and URL name (diffed), all links, the provisioning percentage text and bar width, the "Assigning..." IP fallback, `order_table.html` (shared partial, left for Batch 5). These two pages contain no JavaScript and nothing polls them.
Not added: no new data, counts or buttons.

### Batch 3 visual approval
- On 2026-10-13 the project owner reviewed the Batch 3 preview and reported being happy with its appearance.
- This approval is limited to what the owner reviewed. States the owner did not report seeing (for example a provisioning server, a failed server, the empty states, phone width) and any functional, keyboard or screen-reader checks are not marked as passed.

## Completed — Batch 4 (VPS detail, provisioning status)
Changed files:
- `portal/templates/portal/vps_detail.html`: one change, `class="back-link"` on the "My VPS" link. The `<script>` block, forms, CSRF tokens, IDs, `data-*` attributes, conditions and URL names are untouched.
- `portal/templates/portal/provisioning_status.html`: two additive changes. (1) The root card gets ` provisioning-failed` when the server-rendered `order.status == 'FAILED'` (the script is not included for FAILED, so the red state previously only appeared after a poll); (2) `class="provisioning-warning"` added next to `id="provisioning-warning"`. The `<script>` block and every ID/data attribute are untouched. This partial is also included by `order_detail.html`, `invoice.html` and `payment_return.html`, so the new look appears there as well.
- `portal/static/portal/portal-modern.css`: new "Server management and provisioning" section: global `[hidden]{display:none!important}` (protects JS `hidden` toggles from any `display` rule), card-style provisioning status with teal accent edge and red failed state, thinner progress bar, cleaner stage pills/wait box/meta row, two-column management grid (a lone last card spans the row), ruled detail lists, grid-based connection boxes with copy buttons (no absolute positioning, stacked on phones), styled Windows password box with a secondary Hide button, tidy power controls and help text, dashed "preparing" cards, full-width stacked power buttons on phones.

Constraints honoured: #runtime-state, #setup-vps-state and #setup-access-state have their `className` overwritten by the page scripts, so they are styled only through parent selectors and existing state classes; copy buttons stay text-only because the script stores and restores `textContent`; no ARIA values were added to the progress bar because the script does not update them (a static value would go stale).

### Batch 4 visual approval
- On 2026-10-14 the project owner reported approving the Batch 4 appearance "for the appearance I reviewed".
- Visual approval only, limited to what the owner looked at. States the owner did not report seeing (for example live waiting-for-access timers, a Windows server still waiting for RDP, tablet widths) and all functional, keyboard and screen-reader checks stay unverified.

## Completed - Batch 5 (plans, checkout, orders, invoices, payment, web hosting)
Changed files:
- `portal/templates/portal/base.html`: stylesheet cache-bust query changed from `redesign-1` to `redesign-5` (three links) so previews pick up the new CSS.
- `plans.html`: `plan-description`, `plan-yearly`, `page-intro` classes only.
- `select_plan.html`: checkout step line now has a `<span>` per step with the current step marked `aria-current="step"` (same text); section classes `checkout-layout`, `plan-summary`, `plan-config`, `plan-prices`; form gets `order-form`; submit button gets `type="submit"` and `class="wide"`; help paragraphs get `form-help` (the `#access-help` id, its `muted` class and text are untouched); back link gets `back-link`. The `<script>` block is byte-identical and `form.as_p` is untouched.
- `review_order.html`: step line as above (step 2 current); `details ruled` on the summary list; confirm form gets `confirm-form`; confirm button gets `type="submit"` and `class="wide"`; "Change selection" paragraph gets `change-selection`. Hidden `checkout_token` field, CSRF token, `action` URL, amount and all conditions untouched.
- `orders.html`, `invoices.html`, `order_table.html`: `page-intro`; `data-table` on the tables; `num` on the Amount header and cells (right-aligned figures); the empty header cell in the invoices table now contains visually hidden text "Actions" (screen-reader label); the empty-state "Explore plans" link is now a small button and its trailing arrow was dropped (same change as the approved Batch 3 dashboard empty state). `order_table.html` is also included by the dashboard, so the dashboard's recent-orders table picks up the new table styling.
- `order_detail.html`: heading wrapped in the existing `page-heading` pattern (eyebrow, h1 and status badge, same as invoice); `back-link`; `details ruled`.
- `invoice.html`: `back-link`, `invoice-parties`, `details ruled`, `data-table`, `num`.
- `pay_button.html`: `payment-notice` added to the existing `notice` div. Forms, CSRF, button text and every condition untouched.
- `payment_return.html`: `payment-result` on the card; `payment-message` plus `payment-confirmed` / `payment-unavailable` / `payment-pending` on the status paragraphs. No new conditions.
- `checkout_error.html`: `error-message` on the existing `role="alert"` paragraph.
- `portal/static/portal/portal-modern.css`: new "Plans, checkout, orders, invoices and payment" section (plan cards, checkout steps, form layout and radio rows for billing cycle, ruled key/value lists, table number alignment, pagination buttons, invoice layout, payment notice states, phone rules). `.visually-hidden` utility added.
- `portal/static/portal/storefront.css`: FAQ summary marker moved inside the list margin; spacing before the paragraph that follows the "What happens next" list on web hosting. No other web-hosting change.
- `web_hosting.html`, `pagination.html`, `provisioning_status.html`, `vps_detail.html`: no template change (hosting and pagination were already covered by the Batch 1 storefront styles and the new pagination rules).

Design decisions: payment-pending notice uses the warning (amber) palette with a left accent like the provisioning card; confirmed/unavailable payment messages use success/danger tints; money figures are right-aligned with tabular numerals; no gradients, hover lift or new motion.

Kept exactly as before: all Django tags and variables (sequence diffed per template), URL names, form actions, hidden fields, CSRF tokens, prices, conditions, `select_plan` script and its IDs, provisioning partial and its script, payment and provisioning behavior.

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

### Batch 2 checks (performed 2026-10-13)
- Project test suite `portal.tests` + `portal.test_storefront` (35 tests, includes registration, login redirect, logout, account update, permission and CSRF tests) run against a throwaway in-memory SQLite settings file kept outside the repository: 35 passed. Other test modules (`test_provisioning`, `test_vps_control`, `test_windows`, `test_xendit`, `test_ssh_endpoint`) were not run.
- Rendered login, register (empty and invalid submission) and account pages with the Django test client against both the Batch 1 templates and the new ones: field names, labels, validation messages, CSRF token presence, form methods, hidden `next` value, in-page links, headings and required/invalid counts are identical. Account POST saves the profile (same result as before).
- Django tags/variables in the three templates are identical to the previous versions (diffed).
- CSS brace balance for `portal-modern.css`: OK.

### Batch 3 checks (performed 2026-10-13)
- Full project suite `manage.py test portal` (146 tests) run against a throwaway in-memory SQLite settings file kept outside the repository: 146 passed, system check reported no issues. This includes the existing dashboard scoping, My VPS scoping/IP, "Manage VPS" and "Your VPS servers" tests.
- Rendered dashboard and My VPS with the Django test client against both the previous templates and the new ones, with an empty account and with seeded paid ACTIVE, PROVISIONING (0% and 42%), FAILED and PAID orders, a PENDING order, and another customer's order: visible text, hrefs, badge classes/labels, progress widths, IP values, form/script counts and h1 are identical, except the empty-state link text lost its trailing arrow. Other customer's server did not appear.
- Django tags/variables diffed: only additions are `order.status|lower` and `order.provisioning_progress` reused for the new class/attributes.
- CSS brace balance OK. Contrast computed for new combinations: neutral badge 6.57:1, muted text on empty-state background 5.52:1, link on that background 5.68:1.

### Batch 4 checks (performed 2026-10-13)
- Full project suite `manage.py test portal` (146 tests) on a throwaway in-memory SQLite settings file kept outside the repository: 146 passed, system check clean.
- Rendered `vps_detail`, `order_detail` and `invoice` for 7 states (Linux active; Linux active without SSH details; Linux provisioning; provisioning with error; Windows active with RDP; Windows active without RDP; failed) = 21 pages, from the previous and new templates. Result: `<script>` bodies byte-identical on 21/21; apart from `class` attributes the markup is identical on 21/21 (after normalising CSRF tokens and render timestamps); the only class changes are the three listed above (back-link on 7 pages, `provisioning-failed` on the 3 FAILED pages, `provisioning-warning` on 3 pages).
- JavaScript: CORRECTION (2026-10-14): the repository DOES have a JS test file, `portal/test_provisioning_poll.cjs` (an earlier version of this note wrongly said there were no JS tests). See "JavaScript test record" below. In addition, a throwaway jsdom harness (kept outside the repository, not committed) ran the real inline scripts of all 21 rendered pages with mocked `fetch`, clipboard and `confirm`, so no request or power command could reach infrastructure. Behaviour was identical before and after on 18/21 pages, and on the other 3 (FAILED pages) the only difference is the intended `provisioning-failed` class present at load. Observed on the new pages: power state transitions (running, stopped, command running, command needing review, status unavailable) set the correct text, state class, enabled/disabled buttons and help text; confirm dialogs cancel Shutdown/Reboot on "No" and allow them on "Yes", Start has none; copy buttons copy the right values, show "Copied" then restore, and show "Copy failed" when the clipboard rejects; Windows password reveal sends a POST with the CSRF header, fills the read-only field, copies it, hides on request, auto-hides after the timer, and shows the failure message when the request fails; provisioning polling updates percent, bar width, step, VMID, IP and stage pills, shows the wait box when active without access details, triggers one page reload on activation, and marks the card failed on a FAILED poll. Zero script errors.
- Screenshots (Chromium, all network mocked, local CSS) of vps_detail for 6 states at 1280px and 390px reviewed by the assistant: no horizontal overflow in any of the 12; layout issues found (divider gaps, centred title on phones) were fixed and the affected states re-checked (Linux active, Windows with revealed password, provisioning on phone; Linux active, provisioning and failed on desktop).
- Contrast computed for new combinations: failed card text 6.17:1, warning text 6.34:1, meta/help text on tinted background 5.52:1, stage pills 5.76-6.28:1, white on teal buttons 5.13:1. Disabled power buttons (4.09:1) are disabled controls.

### JavaScript test record (performed 2026-10-14)
- Command: `node --test portal/test_provisioning_poll.cjs`, run in a fresh clone of `design/portal-redesign` at `92b5bb6c700fc29a249b7e754b08b6e4895087a7` (Node v22.22.0).
- Result: 9 tests, 9 passed, 0 failed, 0 cancelled, 0 skipped (about 139 ms). Exit code 0.
- What it covers: it reads `portal/templates/portal/provisioning_status.html`, extracts the real inline `<script>` and runs it in a Node `vm` with a minimal fake browser and delayed replies. Tests: activation reload with RDP still preparing; Windows polling until RDP is ready; Linux waiting for SSH; no endless polling/reload on a fully rendered page; failure stops polling and keeps the order reference; fetch errors retry; wait copy and status-check counting; long-wait help text; wait start survives reload and clears on readiness.
- What it does not cover: `vps_detail.html` scripts (power controls, copy buttons, password reveal), `select_plan.html` script, any CSS or layout. Those remain covered only by the temporary mocked harness described under Batch 4 checks, which supplements (does not replace) this test file.
- VM200 (preview server) cannot run this command because Node.js is not installed there. The result above comes from this clone, not from VM200.
- Test file and script bodies are unchanged by the redesign (Batch 4 left the `<script>` block byte-identical).

### Batch 5 checks (performed 2026-10-14)
- Full project suite `manage.py test portal` (146 tests) on a throwaway in-memory SQLite settings file and virtualenv kept outside the repository: 146 passed, before and after the changes; `manage.py check` clean. Other settings (.env, PostgreSQL) not used.
- `node --test portal/test_provisioning_poll.cjs`: 9 of 9 passed after the changes.
- Before/after render comparison with the Django test client on the same seeded database (alice with orders in PENDING, OVERDUE invoice, no invoice, PROVISIONING 42%, ACTIVE, FAILED, CANCELLED/VOID plus 24 extra paid orders; a second customer; an empty customer): 39 pages (plans signed out/in, web hosting, select plan GET/invalid POST/Windows-enabled, review order Linux and Windows, checkout error, orders pages 1-2 and empty, invoices pages 1-2 and empty, order detail and invoice for 7 states, invoice/order with Xendit enabled in the no-checkout, CREATING and ACTIVE states, overdue invoice, payments disabled, payment return for pending, paid-provisioning, paid-active and unavailable). Xendit was only simulated with fake setting values and database rows; no request to any payment or infrastructure service was made. Result: script bodies byte-identical on 39/39; Django tag/variable sequences identical in every template; ignoring `class` attributes and layout wrappers, the only differences are the intended ones: step-line spans (5 pages), `type="submit"` on 3 buttons (5 pages), "Explore plans" arrow removed (2 empty states), hidden "Actions" header text (2 invoice lists). Other customer's data did not appear.
- Real-browser (headless Chromium, all network mocked, local CSS) check of the `select_plan` script on the Windows-enabled page, before and after: initial Linux state, switching to Windows 11 (SSH key field disabled, not required, its paragraph hidden, help text changed) and back to Ubuntu (restored) are identical, no script errors.
- Screenshots of all 39 pages at 1280px and 390px reviewed by the assistant: no horizontal page overflow on any of the 78 after fixes. Issues found and fixed during review: hidden header text widening the page on phone invoices lists, help text touching the submit button, double rule under the plan summary, stagger in ruled lists on phone, cramped invoice table on phone, FAQ markers outside the margin and a paragraph touching the list on web hosting.
- CSS brace balance OK for all three files. Colour pairs used for the new notices reuse the already-computed tokens (warning 6.34:1 on its tint, danger 6.17:1, white on teal 5.13:1); success text on its tint (#17603e on #e2f5ec) and the current-step link colour were not separately calculated.

## Not yet checked (needs a real browser or the running site)
- Batch 4: owner approved the appearance of what they reviewed (2026-10-14). Not reported as seen and not verified: the waiting-for-access box with live timers, a Windows server still waiting for RDP, the password box on phone width, tablet widths. The assistant's Batch 5 screenshots did show the provisioning card inside order detail, invoice and payment return (mocked data).
- Batch 5 has NOT been reviewed by the owner. Everything above under Batch 5 checks used mocked or seeded test data in headless Chromium and the Django test client, not the real preview site. Not verified: the real Xendit redirect, the Pay Now / Continue Payment buttons submitting (never triggered; no real payment), the order confirmation POST creating an order (covered only by existing Django tests), the live provisioning card on the invoice and order pages, real web-hosting data from Hestia, tablet widths, keyboard order, focus visibility and screen-reader behaviour of the new checkout step markers, radio rows and hidden header text.
- No real VPS power command, password reveal, clipboard permission prompt or live polling was exercised; all were mocked. Real-browser clipboard behaviour (HTTPS requirement, permission prompts) is unverified.
- Keyboard tab order, focus visibility and a screen-reader pass are still to be run on all pages.
- Batch 3 states not reported as reviewed by the owner (provisioning/failed servers, empty states, phone width) and validation-error styling on login/register/account remain unconfirmed.
- Pages not yet restyled: none remain in the plan. Final pass items (keyboard, focus, screen reader, unused legacy CSS) are still open.
- The real site configuration (.env, PostgreSQL) has not been used by the assistant; tests ran on SQLite.

## Known problems / risks
- The bare `.active`, `.pending`, `.paid`, `.failed`, `.cancelled` classes in `portal.css` style any element with those class names, not only `.badge`. Nav links use `.active` and are overridden by `.main-nav a.active`; left as is for now.
- `.nav-wrap` and `.container` share one width (1240px); previously 1200px vs 1240px.
- Cancelled orders/invoices (and void invoices) show a neutral grey badge instead of red. Revert `.badge.cancelled, .badge.void` in `portal-modern.css` if red is preferred.
- Dashboard greeting prints "Welcome, ." if a customer's full name is empty (existing behaviour, left unchanged).
- Dashboard "Active VPS" counts active subscriptions while the server list shows paid orders in several states, so they can differ (existing behaviour).
- On `vps_detail`, a FAILED server still shows the "Preparing remote access" spinner and message because the template only checks SSH/RDP fields (existing behaviour, left unchanged because it is a template condition).
- The provisioning progress bar is not exposed as a progressbar to assistive technology; doing so needs the script to update ARIA values, which is out of scope.
- The global `[hidden]{display:none!important}` rule affects any element using the `hidden` attribute across the site; this is intended.
- Pages that include the provisioning partial (order, invoice, payment return) use the Batch 4 card style.
- Batch 5: on phones the orders table (7 columns, shared with the dashboard) still scrolls sideways inside its card; the page itself does not overflow. Stacking rows into cards would need extra attributes on every cell and was left out. The invoice table is compacted for phones instead.
- Batch 5: the empty-state "Explore plans" links lost their trailing arrow (matches the approved dashboard empty state). Revert in `order_table.html` and `invoices.html` if the arrow is preferred.
- Batch 5: the cache-bust query is now `redesign-5`; production would need the same stylesheet files collected if this is ever merged.
- Batch 5: `:has()` is used for the checked billing-cycle highlight and the review total label; browsers without it show the plain styles (still usable).
- Batch 5: `payment-notice` is amber for every "Pending payment" state, including when online payments are unavailable.

## Current task and exact next step
Batch 5 is complete and pushed, pending the owner's visual review (NOT yet reported). All planned page batches are now done; nothing is merged or deployed. Next:
1. Owner: preview on VM200 (hard refresh; stylesheet version is `redesign-5`): VPS plans, a plan's select page (switch the operating system between Linux and Windows if Windows ordering is enabled; submit only with test data), the review page, My orders (including page 2 if present and the empty state), an order detail page, My invoices, an invoice with a Pending payment box (do NOT press Pay Now or Continue Payment unless test payments are intentionally enabled), a paid invoice with the provisioning card, the payment-status page, and Web hosting; desktop and phone width. Report anything off.
2. After Batch 5 approval: final pass. Keyboard and focus review, screen-reader spot check, remove unused legacy CSS in `portal.css`, recheck every page at tablet width, then final owner sign-off.
3. The owner decides about merging into `codex/windows-rdp`; deployment is separate. Do not merge or deploy until asked.

## Save state
- Earlier commits: Batch 1 `5d46b2c`, `d283cb0`; Batch 2 `e1b176a`; Batch 3 `e4f14e5`. Batch 4 `92b5bb6`; status/JS-test record update `fae6ef9`. Batch 5 is committed on `design/portal-redesign` and pushed to `origin/design/portal-redesign`; get the latest hash with `git log -1 --format=%H origin/design/portal-redesign` (a commit cannot contain its own hash).
- `origin/codex/windows-rdp` is unchanged at `738156c`. Nothing is merged or deployed. No uncommitted work as of this update.
