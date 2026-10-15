# Frontend redesign status — ICT Ventures Cloud Portal

Last updated: 2026-10-14 (final accessibility, layout and CSS cleanup pass).

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
Direction: calm, flat and readable. Colour scheme is the blue palette below (changed from the original navy + teal on 2026-10-14; see "Colour palette change"). Remove gradients, blur, hover-lift and decorative shapes. Keep only functional motion (progress bar, spinner), and respect reduced motion.

Tokens live at the top of `portal/static/portal/portal.css` (`:root`):
- Surfaces: `--bg #F5F7FB` (page), `--surface #FFFFFF` (cards), `--surface-alt #F8FAFC` (table headers, inset boxes), `--line #E2E8F0` (borders), `--neutral-bg #F1F5F9`.
- Text: headings and strong text `--ink #14213D`, body `--text #334155`, secondary `--muted #617187` (see palette note), neutral badge text `--neutral-text #475569`.
- Primary: `--primary #2563EB` (white on it 5.17:1), `--primary-hover #1D4ED8` (6.70:1), selected/active background `--primary-soft #EFF6FF`, primary-tinted borders `--primary-line #BFDBFE`, links `--link #2563EB`.
- Dark sections: `--navy #14213D`, `--navy-raised #1C2B4D`, `--on-navy #CBD5E1`, `--on-navy-muted #A9B7CB`, `--accent-on-navy #93C5FD`.
- Status (unchanged): success/warning/danger text + background pairs stay green, amber and red.
- Form control border `--control-border #7B8BA3` (3.46:1 on white, meets 3:1 for controls). The requested border colour #E2E8F0 is only 1.2:1, so it is used for card/table/divider borders, not form controls.
- Focus ring `--focus #2563EB`, 3px, offset 3px (light ring on navy sections).
- Radius: `--radius 12px` (cards), `--radius-sm 8px` (controls). Hero 16px.
- Spacing scale: `--space-1..8` = .25, .5, .75, 1, 1.5, 2, 3, 4.5 rem. Content width `--content-width 1240px` (header and page content now share it).
- Type: Inter / Segoe UI / system-ui stack (no web font loaded), 16px base, 1.6 line height, heading tracking -.02em, h1 `clamp(1.85rem, 3vw, 2.3rem)`.
- Components so far: header + nav (`.main-nav`), buttons (`.button`, `.button.secondary`, `.button.small`), cards, notices, form controls, tables, badges, footer, pagination, storefront hero/sections/FAQ/banner.

CSS load order (unchanged): `portal.css` (tokens + page components + JS-state classes) → `portal-modern.css` (shared shell/controls) → `storefront.css` (public pages). All three links in `base.html` carry a `?v=redesign-N` cache-busting query (currently `redesign-6`).

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

### Batch 5 visual approval
- On 2026-10-14 the project owner reported approving the Batch 5 appearance "for the pages I reviewed".
- Visual approval only, limited to the pages the owner looked at. It does not cover pages or states not reviewed, and no functional, keyboard, screen-reader or payment checks were reported. The approval was given on the teal colour scheme; the blue palette below has NOT been reviewed.

### Colour palette visual approval
- On 2026-10-14 the project owner approved the blue palette, including the three contrast adjustments (secondary text `#617187`, control borders `#7B8BA3`, derived colours for unspecified surfaces).
- Visual approval only, limited to the pages the owner reviewed. Functional, keyboard and screen-reader behaviour on real pages were not reviewed by the owner.

## Completed - Colour palette change (teal to blue, requested 2026-10-14)
Colour-only change. Layout, spacing, typography, markup, scripts and functionality untouched.
Changed files:
- `portal/static/portal/portal.css`: `:root` tokens replaced (see Agreed design system), new tokens `--text`, `--neutral-bg`, `--neutral-text`; `h1,h2,h3` now use `color: var(--heading-color, var(--ink))` so headings are #14213D while body text is #334155 (dark sections set `--heading-color: #fff`, see storefront.css); hard-coded greys (`#e5eaf1`, `#e7ecf3`, `#edf0f5`, `#46566a`, `#edf1f6`, `#aebbd0`, `#eef3f9`, `#d6dde8`, `#667684`) replaced with tokens. Green success, amber warning and red error colours, the runtime-state dots and the provisioning "complete" green were left as they were.
- `portal/static/portal/portal-modern.css`: body text colour, shadow tint, notice/provisioning/payment text use body colour, neutral badges use tokens, failed provisioning card secondary text uses the danger colour (it fell below 4.5:1 on the red tint with the new secondary colour).
- `portal/static/portal/storefront.css`: dark-section accents, hero/banner button colours, hosting availability chip and the accent-card paragraph moved to blue equivalents (`#93C5FD` accent, `#BFDBFE` hover, `#DBEAFE` chip text, `#8DA2C0` outline button border); dark-section headings forced white through `--heading-color`.
- `portal/static/portal/favicon.svg`: blue square with a white plus (was dark navy with a teal plus).
- `portal/templates/portal/base.html`: stylesheet cache-bust query `redesign-5` to `redesign-6` only.

Deviations from the requested palette (please confirm or reject):
1. Secondary text uses `#617187`, not `#64748B`. `#64748B` measures 4.44:1 on the page background and 4.37:1 on the selected background (below the 4.5:1 AA minimum for normal text); `#617187` is 3% darker and measures 4.64:1 and 4.57:1. It is 4.76:1 on white with the requested value.
2. Form control borders use `#7B8BA3` (3.46:1 on white) rather than `#E2E8F0` (1.2:1, fails the 3:1 non-text minimum for controls). `#E2E8F0` is used for card, table and divider borders.
3. Colours the palette does not specify were derived from it: table header and inset backgrounds `#F8FAFC`, neutral badge `#F1F5F9`/`#475569`, primary-tinted border `#BFDBFE`, dark sections `#14213D`/`#1C2B4D` with light text `#CBD5E1`/`#A9B7CB` and accent `#93C5FD`. The dark hero, banner and VPS-hosting card on the homepage and web hosting page are now navy-blue instead of near-black.

### Colour palette checks (performed 2026-10-14)
- Full project suite `manage.py test portal` (146 tests, throwaway in-memory SQLite, outside the repository): 146 passed; `manage.py check` clean. `node --test portal/test_provisioning_poll.cjs`: 9 of 9 passed. CSS brace balance OK. Only CSS, the SVG favicon and the cache-bust query changed; no other template, Python or script file differs.
- Automated text-contrast audit (headless Chromium, mocked data, desktop width) of 47 rendered pages (storefront home, web hosting, login, register, dashboard, My VPS, account, VPS detail, plans, checkout, orders, invoices, order detail, payments, errors, with seeded pending/overdue/provisioning/active/failed/cancelled states): every visible text element against its effective background, 4.5:1 normal text and 3:1 large text. After the fixes above: 0 failures. Elements with opacity below 1 (disabled controls) and hidden elements were not measured.
- Hover, keyboard focus and disabled states measured in Chromium: primary button white on #2563EB 5.17:1, hover #1D4ED8 6.70:1; secondary button hover #1D4ED8 on #EFF6FF 6.16:1; hero button on navy 8.86:1, hover 11.24:1; active navigation #2563EB on #EFF6FF 4.75:1; inactive navigation 4.98:1, hover 15.27:1; links 5.17:1; pagination hover 4.75:1. Keyboard focus ring is a 3px solid #2563EB outline (light #93C5FD on navy sections) on buttons, links, inputs, selects and the skip link. Disabled power button: text 4.54:1 on #F1F5F9 before its 45% opacity (disabled controls are exempt).
- Screenshots of all pages at 1280px and 390px: no horizontal overflow; the assistant looked at homepage, dashboard, a failed invoice and the earlier checkout/payment pages. Not every page was individually inspected after the colour change.
- A search of all stylesheets and the favicon found no remaining teal colour values.
- Not verified: the real preview site, real browsers other than headless Chromium, Windows high-contrast mode, any state not rendered above (for example live provisioning progress colours, the Windows password box), colour-blindness simulation, and keyboard order or screen-reader behaviour.

## Completed - Final pass (keyboard, screen reader, tablet/phone, unused CSS; 2026-10-14)
Changed files (all presentation or additive attributes; no script, Python, form or Django-logic change):
- `portal/templates/portal/base.html`: stylesheet cache-bust `redesign-6` to `redesign-7`; a line break between the brand name and "Cloud Portal" inside the logo link so its visible text ("ICT Ventures Cloud Portal") is part of its accessible name (axe `label-content-name-mismatch`; layout unchanged because the two items are grid children).
- `portal/templates/portal/provisioning_status.html`: the empty progress-bar track had `aria-label` but no role (axe `aria-prohibited-attr`); it is now `aria-hidden="true"` because the percentage, step text and stage pills next to it carry the same information. The `<script>` block, IDs and data attributes are untouched.
- `portal/static/portal/portal-modern.css`: underline on the "Sign in" / "Create an account" link in the auth pages (axe `link-in-text-block`, links must not rely on colour alone); `white-space: nowrap` on the last two table columns (dates and invoice numbers) plus 8px horizontal cell padding at 900px and below so the invoice column fits at tablet width; clearer secondary text on the red failed provisioning card (already in the palette commit).
- `portal/static/portal/storefront.css`: at tablet width the third web-hosting package now spans the row instead of sitting at half width with an empty half beside it.
- `portal/static/portal/portal.css`: removed legacy rules that are verified unused (below).

### Final pass checks (performed 2026-10-14, headless Chromium with mocked data; Django test client for rendering)
- Keyboard: tabbed through 47 rendered pages (749 tab stops): no positive `tabindex`, skip link and `#main` target on every page, tab order follows reading order, no keyboard traps, tab stop count equals the number of tabbable elements (radio groups count once; login and register start after the username field because Django adds `autofocus` to it), every stop has a visible focus indicator (3px outline, offset 3px) and the ring contrast against the surrounding background is at least 3:1 (blue on light surfaces, light blue on navy sections).
- Screen reader: axe-core 4.14.0 (WCAG 2.0/2.1/2.2 A and AA plus best-practice rules) on all 47 pages found 3 issue types (above); all fixed; re-run: 0 violations. Structure check on 47 pages: exactly one h1, no skipped heading levels, banner/navigation/main/contentinfo landmarks, page language and title present, every table has header cells (Chrome exposes them as column headers). Accessibility-tree dumps of the plan configuration, order detail and orders pages were read: logo, navigation (labelled), headings, form controls, buttons and the order table read sensibly.
- Colour: the contrast audit was re-run after these changes: 0 failures on 47 pages.
- Layout: 47 pages at 360, 390, 768 and 1024px (188 combinations): no horizontal page overflow, nothing outside the viewport except inside scrollable table wrappers, no button, input, select or navigation control smaller than 24x24px. Screenshots at 768px of VPS detail, web hosting, orders, invoices and dashboard were looked at; two tablet problems were found and fixed (half-width third hosting package, wrapped invoice numbers and dates). At 390px and below the orders and dashboard tables still scroll sideways inside their card.
- Unused CSS: every class and id in the three stylesheets was compared with whole class tokens in all templates (all conditional branches are present in template source), inline script text, Python files (including form widget attributes) and the JavaScript test. Selectors that only look unused but are generated at run time were kept: `.helptext`, `.errorlist` and `#id_billing_cycle` (Django form output), `.overdue`, `.cancelled` (status badges built from `{{ status|lower }}`) and `.server-card-provisioning` / `.server-card-failed` (built from `server-card-{{ status|lower }}`). Only these were verified unused and removed from `portal.css`: `.hero`, `.hero h1` (also their 800px overrides), `.hero-card`, `.steps`, `.steps li`, `.steps span`. Pixel check: 47 pages at 390, 768 and 1280px (141 screenshots) were hashed before and after the removal; all identical (the register page's autofocus caret makes it flicker between runs and was confirmed to match). Not removed: the `--space-7` and `--space-8` tokens (unused but part of the documented spacing scale) and rules that are only overridden later (not unused).
- Tests: full project suite `manage.py test portal` 146 of 146 passed (throwaway in-memory SQLite outside the repository), `manage.py check` clean; `node --test portal/test_provisioning_poll.cjs` 9 of 9 passed; script bodies byte-identical on 47 of 47 rendered pages compared with the pre-Batch-5 templates; the `select_plan` script behaves identically in Chromium (Windows hides and disables the SSH key field, Linux restores it). CSS brace balance OK.

### Still unverified after the final pass
- Not tested with a real screen reader (NVDA, JAWS, VoiceOver, TalkBack), real keyboard on the preview site, real iOS or Android devices, other browsers than headless Chromium, Windows high-contrast or forced-colours mode, zoom to 200 or 400 percent, or text-size changes. Automated checks cannot prove the page reads well aloud.
- Dynamic states were only exercised with mocks or not at all: live provisioning updates and the waiting-for-access timers are not announced to screen readers (the script updates text without a live region; adding one needs a script or template change that was out of scope and could repeat announcements on every poll), VPS power controls, password reveal, copy buttons, clipboard prompts, the real Xendit redirect, real Hestia data. Contrast of those states was not separately measured.
- The billing cycle radio buttons come from Django's `RadioSelect` without a group role or name, so some screen readers announce "Monthly, radio button" without the "Billing cycle" prompt. Fixing it means changing form output or adding script, both out of scope.
- Login and register put focus in the username field on load (Django `autofocus`), so keyboard and screen-reader users begin inside the form rather than at the skip link; unchanged form behaviour.
- The orders and dashboard order tables (7 columns) scroll sideways on phones; the scrolling region is not announced as scrollable.
- Anything the owner did not review remains unreviewed: pages and states not looked at on the preview site, tablet widths (only reviewed by the assistant from screenshots), and everything functional.

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
- Batch 5: owner approved the appearance of the pages they reviewed (2026-10-14), on the teal scheme. Pages or states they did not review, and everything functional, remain unverified. The following list is what was never verified: everything above under Batch 5 checks used mocked or seeded test data in headless Chromium and the Django test client, not the real preview site. Not verified: the real Xendit redirect, the Pay Now / Continue Payment buttons submitting (never triggered; no real payment), the order confirmation POST creating an order (covered only by existing Django tests), the live provisioning card on the invoice and order pages, real web-hosting data from Hestia, tablet widths, keyboard order, focus visibility and screen-reader behaviour of the new checkout step markers, radio rows and hidden header text.
- No real VPS power command, password reveal, clipboard permission prompt or live polling was exercised; all were mocked. Real-browser clipboard behaviour (HTTPS requirement, permission prompts) is unverified.
- Keyboard order, focus visibility and an automated screen-reader pass were run on rendered test pages (see Final pass checks); real assistive technology and real-site checks are still open.
- Batch 3 states not reported as reviewed by the owner (provisioning/failed servers, empty states, phone width) and validation-error styling on login/register/account remain unconfirmed.
- Pages not yet restyled: none remain in the plan. The final pass is done; its unverified items are listed under "Still unverified after the final pass".
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
- Colour change: the palette-driven choices listed under "Deviations from the requested palette" are awaiting the owner's confirmation. Status colours (green, amber, red) were not changed and were not re-tuned against the new blue backgrounds beyond the automated contrast audit.
- Colour change: the cache-bust query is now `redesign-6`; a browser that ignores query strings could still show old teal CSS until a hard refresh.
- Batch 5: on phones the orders table (7 columns, shared with the dashboard) still scrolls sideways inside its card; the page itself does not overflow. Stacking rows into cards would need extra attributes on every cell and was left out. The invoice table is compacted for phones instead.
- Batch 5: the empty-state "Explore plans" links lost their trailing arrow (matches the approved dashboard empty state). Revert in `order_table.html` and `invoices.html` if the arrow is preferred.
- Batch 5: the cache-bust query is now `redesign-5`; production would need the same stylesheet files collected if this is ever merged.
- Batch 5: `:has()` is used for the checked billing-cycle highlight and the review total label; browsers without it show the plain styles (still usable).
- Batch 5: `payment-notice` is amber for every "Pending payment" state, including when online payments are unavailable.

## Current task and exact next step
All planned redesign batches, the blue palette and the final pass are complete and pushed to `design/portal-redesign`, pending the owner's review of the final pass (NOT yet reported). Nothing is merged or deployed. Next:
1. Owner: preview on VM200 with a hard refresh (stylesheet version `redesign-7`). Press Tab through a few pages (the skip link, navigation, forms and buttons should show a blue ring), look at tablet width (about 768px) on web hosting, orders, invoices and the dashboard, and glance at the pages changed in this pass: the logo link, a provisioning card, login/register, and web hosting. Do not press Pay Now or Continue Payment unless test payments are intentionally enabled. Report anything off.
2. If time allows, test with a real screen reader and on a real phone and tablet (see "Still unverified after the final pass").
3. The owner decides about merging `design/portal-redesign` into `codex/windows-rdp` and about deployment; neither has been done and neither will be done without an explicit request.

## Save state
- Earlier commits: Batch 1 `5d46b2c`, `d283cb0`; Batch 2 `e1b176a`; Batch 3 `e4f14e5`. Batch 4 `92b5bb6`; status/JS-test record update `fae6ef9`; Batch 5 `71dff2d`; blue palette `8722710`. The final pass is committed on `design/portal-redesign` and pushed to `origin/design/portal-redesign`; get the latest hash with `git log -1 --format=%H origin/design/portal-redesign` (a commit cannot contain its own hash).
- `origin/codex/windows-rdp` is unchanged at `738156c`. Nothing is merged or deployed. No uncommitted work as of this update.

## Integration verification — 15 October 2026

Combined deployed staff/account revision cbb002e with redesign 3f176d7
on integration/portal-redesign. Resolved the base.html navigation conflict
by retaining staff/customer separation and the redesigned accessibility attributes.

User-executed verification on VM200:
- All 188 Django tests passed on temporary SQLite.
- Django system checks passed.
- No model migration changes detected.
- No unresolved conflicts or staged whitespace errors.

Earlier statements that this checkout contains only the 146-test baseline
are superseded by this integration record.
Combined browser review and PostgreSQL verification remain pending.
Production has not been changed by this integration.
