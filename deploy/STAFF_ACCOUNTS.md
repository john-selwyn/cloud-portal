# Separate staff and customer accounts

Prepared 12 October 2026 on `feature/staff-account-separation`, based on the deployed Management Portal commit `99affd2`. Deployment of this follow-up remains pending until server verification is recorded. It introduces no model or database migrations.

## Staff administration

Sign in to `/management/` with an active staff superuser. The overview provides **Staff accounts** and **Add staff account** links. The sidebar also lists Staff accounts. Ordinary staff cannot open these pages or use their POST/password endpoints, even if they have Django user-management permissions.

To create an employee account:

1. Open **Add staff account** (`/management/auth/user/add/`).
2. Enter a unique username, employee name/email, and an initial password. Enter the password directly in the trusted portal; do not paste it into chats, documentation or source code.
3. Choose **Save and continue editing**.
4. Assign only the required **User permissions** and save.
5. The employee signs in at `/management/login/`. They can change their own password through the header's Change password link.

Creation automatically sets staff status and leaves superuser status false. It does not create a customer profile or send an invitation/email. Initially the account has no business-record permissions. Account creation and edits use Django's admin audit log.

Suggested permission selections:

| Responsibility | Permissions |
| --- | --- |
| View the six business record areas | `portal.view_customer`, `portal.view_order`, `portal.view_vpsplan`, `portal.view_invoice`, `portal.view_payment`, `portal.view_subscription` |
| Edit customer contact details | Add `portal.change_customer` |
| Maintain plans | Add `portal.add_vpsplan`, `portal.change_vpsplan` |
| Reconcile existing provisioning status | Add `portal.change_order` together with `portal.view_order` |

Staff-account administration remains superuser-only regardless of these grants. Financial state editing/deletion protections remain in place. Existing group membership is displayed read-only; a trusted superuser uses the legacy admin if group changes are required. Existing permissions are preserved unless the superuser deliberately changes their selection.

The Staff accounts list contains only users marked as staff. A customer cannot be promoted or edited by posting a customer ID to these staff forms. Superuser identities are inspect-only on this page, protecting the owner's own access from accidental demotion/deactivation here. Superuser maintenance remains with trusted legacy admin tools. Ordinary staff can be deactivated using **Active**; deleting staff accounts is disabled. Deactivation denies subsequent authenticated requests.

## Account and session separation

Customer and staff identities remain in Django's existing user table, distinguished by server-controlled roles. A staff account signs in at Management; the customer login rejects staff credentials. Protected customer dashboard, account, ordering/payment and VPS action views require a non-staff, non-superuser customer account. Public storefront pages remain available.

New staff and superuser creation no longer creates Customer records. Public signup cannot set staff/superuser flags. Customer-profile fallback refuses staff accounts. Customer registration and existing non-staff customer behavior are retained.

Management and legacy admin use separate cookies: `management_sessionid`, `management_csrftoken`, and `management_messages`. Customer cookie names remain unchanged. Both accounts can stay signed in in the same browser; signing out of one leaves the other signed in. CSRF validation and message cookies are separated as well. Cookie security/domain/path/expiry attributes are inherited from Django's existing settings; middleware does not mutate global settings per request. Django's normal session engine, password hashing, authentication and session invalidation remain in use. See [Django session documentation](https://docs.djangoproject.com/en/6.0/topics/http/sessions/).

On rollout, staff must sign in again to establish the new Management session. Existing customer sessions remain usable. An older staff login stored in the customer cookie is denied access to protected customer workflows; use a separate customer account for future customer activity. Clear the old customer-side staff login using customer logout if necessary. The staff and customer accounts should have distinct usernames and independent passwords.

## Existing records

No profile, user, order, invoice, payment or subscription is deleted or reassigned. Customer directory lists/totals exclude staff and superuser identities. Older staff-linked Customer profiles remain in storage and can still be inspected through historical order links, where they are labeled **Historical staff-linked profile**. Business-record totals/history retain those records.

This release does not automatically transfer historical staff-owned services to another customer. If that is needed, verify ownership and plan a separate reviewed reassignment. Customer VPS power/credential/payment flows require a customer account; the Management Portal's existing operational permissions remain authoritative.

## Implementation and verification

- `portal/account_sessions.py`: cookie routing before Django session, CSRF and message middleware.
- `portal/account_access.py`: customer login role checks and protected-customer decorator.
- `portal/staff_admin.py`: superuser-only staff forms, queries, grants, password access and deactivation.
- `portal/signals.py`: customer creation limited to non-staff accounts.
- `portal/management_admin.py` and Management overview: staff links, customer-directory separation and preserved historical links.
- `portal/views.py`, `portal/payment_views.py`, project URLs/settings and navigation: account-role integration.
- `portal/test_account_separation.py`: 20 new security/workflow tests; existing Management fixtures now use separate customer identities and staff sessions.

Verification on 12 October 2026: the full 188-test suite passed on SQLite, then the final 42 account/Management tests passed after the customer-directory adjustment. The full final 188-test suite also passed on isolated local PostgreSQL 17.11 in 87.747 seconds, including the directory adjustment. Django checks passed, `makemigrations --check --dry-run` reported no changes and `git diff --check` was clean. Browser review with synthetic data verified superuser overview navigation and the staff creation form. Test integrations were mocked and databases were disposable; no production credentials or staff accounts were created by tests. The temporary PostgreSQL process was stopped after verification. This feature has no generated model migrations.

The cookie/security tests cover simultaneous customer and staff identities, independent logout, cross-role session replay rejection, CSRF separation, preserved cookie security attributes and isolation of staff messages from customer pages. Staff-administration tests cover superuser-only access, forged privilege fields, customer-ID rejection, audit attribution, deactivation, protected superuser identities and preserved historical records. The exact local checks were `python manage.py test --noinput`, `python manage.py test portal.test_account_separation portal.test_management --noinput`, `python manage.py makemigrations --check --dry-run`, and the existing workstation-local `python -u management_pg_test.py` helper described in the Management Portal guide.

## Deployment and rollback

Use a reviewed fast-forward code rollout from `99affd2`, after checking the server's current commit and tracked changes and preserving a rollback branch. Run Django checks and inspect `migrate --plan`; no migration operations are expected. Collect static files and restart the existing application service. The restart briefly interrupts requests. Confirm owner/staff login, Staff accounts/Add staff account, customer login and separate logout behavior before calling deployment verified.

Code rollback can return to the preceding compatible Management Portal commit; no schema reversal or record deletion is required. Users/grants created after rollout remain in the database. Before rollback, review those grants and have staff sign in again under the older shared-session behavior. Retain independent customer accounts and do not use rollback as a way to bypass role checks.
