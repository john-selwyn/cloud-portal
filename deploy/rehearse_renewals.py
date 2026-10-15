"""Run only on a separately restored rehearsal database; never use for production rollout."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys

TABLES = ('portal_order', 'portal_invoice', 'portal_payment', 'portal_xenditcheckout',
          'portal_subscription', 'portal_customer', 'portal_vpsplan')
TARGET = ('portal', '0012_renewal_invoice_foundation')


def fingerprint(connection, table, columns):
    digest = hashlib.sha256()
    count = 0
    quoted = ', '.join(connection.ops.quote_name(name) for name in columns)
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT {quoted} FROM {connection.ops.quote_name(table)} ORDER BY id')
        while rows := cursor.fetchmany(500):
            for row in rows:
                digest.update(json.dumps(row, default=str, sort_keys=True, separators=(',', ':')).encode())
                digest.update(b'\n')
                count += 1
    return {'count': count, 'sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', required=True, help='Existing portal environment file; read only, never displayed.')
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true', help='Apply migration only to the explicitly named restored copy.')
    args = parser.parse_args()
    if not re.fullmatch(r'cloud_portal_renewal_rehearsal_[0-9]{8}', args.database):
        raise RuntimeError('Refusing a database without the exact rehearsal naming pattern.')
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from dotenv import load_dotenv
    env = Path(args.env).resolve(strict=True)
    load_dotenv(env, override=True)
    original_database = os.environ.get('DB_NAME')
    if not original_database or original_database == args.database:
        raise RuntimeError('Production and rehearsal database names must be distinct and explicit.')
    os.environ['DEBUG'] = 'False'
    os.environ['DB_NAME'] = args.database
    os.environ['DJANGO_SETTINGS_MODULE'] = 'cloud_portal.settings'
    from django.conf import settings
    if (settings.DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql'
            or settings.DATABASES['default']['NAME'] != args.database):
        raise RuntimeError('Unexpected database settings; refusing to continue.')
    for name in ('PROVISIONING_API_URL', 'BILLING_API_SECRET', 'XENDIT_SECRET_API_KEY',
                 'XENDIT_WEBHOOK_TOKEN', 'HESTIA_API_URL', 'HESTIA_API_PASSWORD', 'MONITORING_HOSTS_JSON'):
        setattr(settings, name, '')
    settings.RENEWAL_INVOICING_ENABLED = False
    settings.ALLOW_TEST_PAYMENT = False
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.db.models import F
    from portal.models import Invoice, Subscription
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        if cursor.fetchone()[0] != args.database:
            raise RuntimeError('Actual database identity mismatch; no migration attempted.')
        cursor.execute("SET lock_timeout = '5s'")
        cursor.execute("SET statement_timeout = '180s'")
    print('Verified isolated database:', args.database, flush=True)
    baseline_path = root / 'var' / (args.database + '-baseline.json')
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        if baseline.get('database') != args.database:
            raise RuntimeError('Baseline belongs to a different database.')
    else:
        executor = MigrationExecutor(connection)
        if TARGET in executor.loader.applied_migrations:
            raise RuntimeError('Migration already applied without a saved original baseline; refusing to invent one.')
        baseline = {'database': args.database, 'tables': {}}
        for table in TABLES:
            with connection.cursor() as cursor:
                cursor.execute('SELECT column_name FROM information_schema.columns '
                               "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", [table])
                columns = [row[0] for row in cursor.fetchall()]
            if 'id' not in columns:
                raise RuntimeError('Expected restored table is missing: ' + table)
            baseline['tables'][table] = {'columns': columns, **fingerprint(connection, table, columns)}
        baseline_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(baseline_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(baseline, handle)
        print('Saved private counts/fingerprints only; no customer rows or credentials saved.', flush=True)
    def verify():
        for table in TABLES:
            expected = baseline['tables'][table]
            actual = fingerprint(connection, table, expected['columns'])
            if actual != {name: expected[name] for name in ('count', 'sha256')}:
                raise RuntimeError('Original records changed in ' + table + '; investigate this restored copy.')
            print(f"{table}: {actual['count']} original records unchanged", flush=True)
    verify()
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan([TARGET])
    if any((migration.app_label, migration.name) != TARGET or backwards for migration, backwards in plan):
        raise RuntimeError('Unexpected migration plan; only forward portal.0012 is permitted.')
    print('Pending renewal migration:', len(plan), flush=True)
    if not args.apply:
        print('Read-only rehearsal preflight complete. No schema changes applied.', flush=True)
        return
    call_command('migrate', TARGET[0], TARGET[1], interactive=False, verbosity=1)
    verify()
    if Invoice.objects.exclude(purpose=Invoice.Purpose.INITIAL).exists():
        raise RuntimeError('Unexpected renewal rows in the restored rehearsal database.')
    if Subscription.objects.exclude(renewal_amount=F('order__amount'),
            renewal_cycle=F('order__billing_cycle'), renewal_currency='PHP').exists():
        raise RuntimeError('Agreement snapshot validation failed.')
    call_command('check')
    call_command('generate_renewal_invoices', dry_run=True, stdout=io.StringIO())
    verify()
    print('REHEARSAL PASSED: original records unchanged; agreement snapshots verified; no renewal invoices created.', flush=True)
    connection.close()


if __name__ == '__main__':
    main()
