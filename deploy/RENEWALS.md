# Renewal invoices and admin visibility — phase 1

Prepared 15 October 2026 against deployed monitoring baseline 5bbfaea323019f1394330e4cb6fbb83591f9b9a1. Not deployed; no live invoice generation or database migration performed by development.

## Verification completed

- Full Django suite: 227 tests passed against a disposable PostgreSQL 17.11 cluster on loopback port 55434, then the cluster was stopped. This includes two concurrent workers issuing the same renewal, a preserving migration from the actual 0011 schema with representative invoice/payment/checkout/subscription rows, ambiguous-backfill refusal and refusal to reverse after renewal history exists. This is not verification on production PostgreSQL 18.6 or a restored production dataset.
- Existing provisioning JavaScript suite: 9 passed. Django checks clean; makemigrations --check reports no changes.
- SQLite targeted renewal/migration tests also passed (PostgreSQL concurrency test intentionally skipped there).
- Desktop 1440px and phone 390px renewal views inspected in the in-app browser with clearly labelled synthetic records. Phone page width stayed within viewport. Search by subscription/order, filters, signed confirmation, invoice creation and exact customer invoice link checked. No production customer records were used. Customer renewal detail has no pay/provisioning controls.
- GET rendering and dry run create no invoices. Repeat generation creates one invoice and one audit entry. Stale review, changed price/agreement, unauthorized accounts, CSRF, cross-customer invoice IDs, overdue/inactive/misaligned dates and invalid periods are covered.
- Initial invoices, successful payment evidence, checkout/session identities, existing routes and customer/staff separation remain covered by the combined suite. Provisioning sync preserves expired subscriptions rather than silently reactivating them.

## Approved rules and scope

Owner confirmed original purchase price, invoice preparation within seven days before the next billing date, and individual review of already-overdue services. Notifications and automatic suspension stay off. No saved-card charges or automatic invoice timer is introduced.

The new Management → Renewals page shows upcoming dates, due/overdue services and unpaid renewal invoices, with search, filters and pagination. Staff need both portal.view_subscription and portal.view_invoice. Only an active superuser may confirm generation; it additionally requires RENEWAL_INVOICING_ENABLED=True. Defaults leave generation disabled while the read-only page works. Confirmations use CSRF and a signed, expiring review of the subscription, billing date and agreement. GET requests cannot create invoices. CLI apply requires explicit subscription IDs and an active administrator identity, with the same service guard and audit logging.

Generation locks the order then subscription, checks the reviewed date/agreement, verifies the original successful payment and creates at most one invoice for that subscription/period. Database uniqueness is the second protection. Repeated creation returns the existing record and does not add another audit entry. Existing/VOID invoices are not silently regenerated. Unaligned anniversary dates, inactive/cancelled/expired services, unsupported/missing agreements and already-overdue dates require review. No past-due catch-up invoices or entitlement changes are inferred.

## Schema migration 0012

Invoice.order changes from one-to-one to a protected foreign key. A conditional constraint retains exactly at most one INITIAL invoice per order, and renewal uniqueness is per subscription/period start. Required period fields and a positive interval are checked for renewal rows. Existing invoice IDs/numbers/order links, payment links/transaction identities, checkout references and subscription dates are preserved.

Existing invoices become INITIAL/PHP (the existing Xendit adapter supports PHP). Subscription renewal amount/cycle snapshots are backfilled from the original order only when ownership, cycle and initial invoice amount agree. Ambiguous source data stops the atomic migration rather than guessing. No new invoices are created by migration. New activations snapshot the original agreement. next_billing_date remains the paid-through boundary, with start_date the original calendar anchor; this phase does not advance either date. Month-end and leap-year calculations preserve that UTC anchor.

All purchase payment/provisioning queries explicitly select INITIAL invoices. order.invoice remains an initial-invoice-only compatibility accessor; querysets prefetch that invoice without joining renewal rows into customer service access. Existing order-based invoice URLs still open the initial invoice. A new invoice-ID URL opens the exact authorized invoice; invoice history links use it. Renewal details have no checkout/provisioning controls and honestly say online renewal payment is not yet available.

Provisioning reconciliation no longer turns an existing CANCELLED or EXPIRED subscription ACTIVE merely because a VM is running. It preserves entitlement dates, agreement and status. This is not automatic suspension or new power enforcement.

## Checks and rollout

Before production rollout, take and verify a fresh recoverable database backup, record HEAD/clean tracked changes and stop conflicting billing/web processes during the schema transition. Rehearse against an isolated restored copy of the actual production database with external integrations disabled. The local synthetic PostgreSQL rehearsal is not a production-data rehearsal. Compare original invoice IDs/amounts/order links, payment/checkout identities, subscription dates and row counts before/after; investigate any backfill refusal. Preserve the production .env and monitor units.

Read-only development/rehearsal checks, from the repository as its service account:

```bash
./venv/bin/python manage.py check
./venv/bin/python manage.py makemigrations --check --dry-run
./venv/bin/python manage.py migrate --plan
./venv/bin/python manage.py generate_renewal_invoices --dry-run
```

The dry run makes no writes and lists proposed amount/currency/due/end dates or review reasons. It does not invoke payment providers, notifications or VM APIs. Applying migration changes the live schema and backfills snapshot fields; run only after the backup and restored-copy rehearsal are verified. Do not deploy new code against the old schema or old one-to-one code against a database with renewal rows.

Deploy phase 1 with RENEWAL_INVOICING_ENABLED=False and RENEWAL_INVOICE_LEAD_DAYS=7. After an authorized rollout: migrate during the brief portal maintenance window, collect static files, check and restart Cloud Portal, then verify owner and restricted staff pages, current purchase/return routes, existing customer invoice links and dry-run output. No renewal scheduler is installed.

Pilot generation is a separate data-changing action: review one eligible subscription, enable the feature privately, restart the portal and confirm one invoice in Management. An operator alternative is:

```bash
./venv/bin/python manage.py generate_renewal_invoices --subscription SUBSCRIPTION_ID --dry-run
./venv/bin/python manage.py generate_renewal_invoices --subscription SUBSCRIPTION_ID --actor ADMIN_USERNAME --apply
```

Placeholders are not live commands. Never bulk-apply to all subscriptions at introduction. Because online renewal settlement is not yet implemented, agree a customer-visible pilot/payment procedure before issuing real invoices. Do not mark a renewal paid manually to test entitlement: no entitlement extension exists in this phase.

## Recovery and later work

Disable RENEWAL_INVOICING_ENABLED to stop new generation while retaining review/history. No timer or remote action needs stopping. After any renewal rows exist, old one-invoice code/schema is not a safe rollback: reverse migration raises IrreversibleError before discarding renewal history. Prefer a forward fix; any database restore requires separately reconciling real payments, customer records and running VMs. Never delete financial history to force rollback.

Later: invoice-scoped provider checkout and exactly-once paid-period extension without provisioning; approved grace/late-payment/cancellation rules; durable suspension/reactivation and race checks; optional notifications after owner authorization. Public-IP/network work remains deferred.
