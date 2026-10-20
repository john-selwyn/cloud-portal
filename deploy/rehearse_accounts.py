"""Preflight and migrate only a separately restored customer-accounts database.

Never use this helper for production deployment. Run preflight first, inspect its
output, then explicitly rerun with --apply against the same isolated copy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

TARGET = ('portal', '0012_customer_accounts')
ORIGINAL_TABLES = (
    'auth_user', 'auth_user_groups', 'auth_user_user_permissions', 'auth_group',
    'auth_group_permissions', 'django_admin_log', 'django_session',
    'portal_customer', 'portal_vpsplan', 'portal_order', 'portal_invoice',
    'portal_payment', 'portal_xenditcheckout', 'portal_subscription', 'portal_vpspoweroperation',
)
NEW_TABLES = ('portal_customeremail', 'portal_accountrequestlimit')


class RehearsalRefused(RuntimeError):
    """A structural diagnostic that contains no credentials or row contents."""


def fingerprint(connection, table, columns):
    quoted = ', '.join(connection.ops.quote_name(column) for column in columns)
    # Row hashes are sorted, so every table (including sessions without integer
    # IDs) has a deterministic fingerprint without saving any row or identifier.
    hashes = []
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT {quoted} FROM {connection.ops.quote_name(table)}')
        while rows := cursor.fetchmany(500):
            for row in rows:
                data = json.dumps(row, default=str, sort_keys=True, separators=(',', ':')).encode()
                hashes.append(hashlib.sha256(data).digest())
    return {'count': len(hashes), 'sha256': hashlib.sha256(b''.join(sorted(hashes))).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', required=True, help='Private live env file to read, never display or modify.')
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true', help='Migrate only the named restored copy after saved preflight.')
    args = parser.parse_args()
    if not re.fullmatch(r'cloud_portal_accounts_rehearsal_[0-9]{8}', args.database):
        raise RehearsalRefused('Refusing a target without the exact accounts-rehearsal naming pattern.')
    root = Path(__file__).resolve().parents[1]
    env = Path(args.env).resolve(strict=True)
    if root == env.parent:
        raise RehearsalRefused('Use a separate isolated checkout, not the live env directory.')
    sys.path.insert(0, str(root))
    from dotenv import dotenv_values
    values = dotenv_values(env)
    original_database = values.get('DB_NAME')
    if not original_database or original_database == args.database:
        raise RehearsalRefused('The configured production database must be explicit and different.')
    os.environ.update({key: value for key, value in values.items() if value is not None})
    # Prevent settings.py from loading another .env after the explicit override.
    os.environ.update(PYTHON_DOTENV_DISABLED='1', DB_NAME=args.database, DEBUG='False',
                      DJANGO_SETTINGS_MODULE='cloud_portal.settings')
    from django.conf import settings
    db = settings.DATABASES['default']
    if (db['ENGINE'] != 'django.db.backends.postgresql' or db['NAME'] != args.database
            or settings.BASE_DIR.resolve() != root):
        raise RehearsalRefused('Unexpected application/database configuration; refusing to continue.')
    for name in ('PROVISIONING_API_URL', 'BILLING_API_SECRET', 'XENDIT_SECRET_API_KEY',
                 'XENDIT_WEBHOOK_TOKEN', 'XENDIT_BUSINESS_ID', 'XENDIT_PUBLIC_BASE_URL',
                 'HESTIA_API_URL', 'HESTIA_API_PASSWORD', 'MONITORING_HOSTS_JSON'):
        setattr(settings, name, '')
    settings.ALLOW_TEST_PAYMENT = False
    settings.CUSTOMER_EMAIL_ENABLED = False
    settings.CUSTOMER_REQUIRE_EMAIL_VERIFICATION = False
    settings.RENEWAL_INVOICING_ENABLED = False
    settings.MAILERS = {'default': {'BACKEND': 'django.core.mail.backends.dummy.EmailBackend'}}
    settings.EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), inet_server_addr()::text, inet_server_port()')
            identity = list(cursor.fetchone())
            if identity[0] != args.database:
                raise RehearsalRefused('Connected database identity does not match the requested rehearsal copy.')
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '180s'")
            cursor.execute('SELECT pg_try_advisory_lock(74190620)')
            if not cursor.fetchone()[0]:
                raise RehearsalRefused('Another accounts rehearsal is using this database.')
            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                           "AND pid<>pg_backend_pid() AND backend_type='client backend'")
            if cursor.fetchone()[0]:
                raise RehearsalRefused('Other clients are connected to this restored copy; isolate it first.')
            if not args.apply:
                cursor.execute('SET default_transaction_read_only = on')
        print('Verified isolated database:', args.database, flush=True)
        print('Email, payment, provisioning and monitoring integrations disabled.', flush=True)
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        allowed_portal = set(executor.loader.graph.forwards_plan(TARGET))
        applied = set(executor.loader.applied_migrations)
        if any(item[0] == 'portal' and item not in allowed_portal for item in applied):
            raise RehearsalRefused('Unexpected portal migration history; do not combine with renewal rehearsal.')
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if any((migration.app_label, migration.name) != TARGET or backwards for migration, backwards in plan):
            raise RehearsalRefused('Unexpected migration plan; only forward portal.0012_customer_accounts is permitted.')
        baseline_path = root / 'var' / (args.database + '-accounts-baseline.json')
        if baseline_path.exists() or baseline_path.is_symlink():
            info = baseline_path.lstat()
            if not stat.S_ISREG(info.st_mode) or baseline_path.is_symlink():
                raise RehearsalRefused('The saved baseline must be a regular private file.')
            if os.name == 'posix' and (info.st_mode & 0o077 or info.st_uid != os.geteuid()):
                raise RehearsalRefused('Baseline must belong to this user with mode 600.')
            baseline = json.loads(baseline_path.read_text())
            if (baseline.get('identity') != identity or baseline.get('target') != list(TARGET)
                    or set(baseline.get('tables', {})) != set(ORIGINAL_TABLES)):
                raise RehearsalRefused('Saved baseline does not match this database and migration.')
        else:
            if args.apply:
                raise RehearsalRefused('Run and inspect preflight first; --apply requires its retained baseline.')
            if TARGET in applied:
                raise RehearsalRefused('Migration already applied without a baseline; refusing to invent one.')
            baseline = {'identity': identity, 'target': list(TARGET), 'tables': {}}
            for table in ORIGINAL_TABLES:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT column_name FROM information_schema.columns '
                                   "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", [table])
                    columns = [row[0] for row in cursor.fetchall()]
                if not columns:
                    raise RehearsalRefused('Missing original table: ' + table)
                baseline['tables'][table] = {'columns': columns, **fingerprint(connection, table, columns)}
            baseline_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if os.name == 'posix' and baseline_path.parent.stat().st_mode & 0o022:
                raise RehearsalRefused('Baseline directory must not be writable by other users.')
            descriptor = os.open(baseline_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as handle:
                json.dump(baseline, handle)
            print('Saved private original-column counts/fingerprints; no rows or credentials exported.', flush=True)

        def verify_originals():
            for table in ORIGINAL_TABLES:
                expected = baseline['tables'][table]
                if fingerprint(connection, table, expected['columns']) != {
                        name: expected[name] for name in ('count', 'sha256')}:
                    raise RehearsalRefused('Original records changed in ' + table + '; investigate before continuing.')
                print(f"{table}: {expected['count']} original records unchanged", flush=True)

        verify_originals()
        print('Pending account migrations:', len(plan), flush=True)
        if not args.apply:
            print('PREFLIGHT PASSED: database read only; no schema changes applied.', flush=True)
            return
        call_command('migrate', TARGET[0], TARGET[1], interactive=False, verbosity=1)
        verify_originals()
        from portal.models import Customer, CustomerEmail, AccountRequestLimit
        if Customer.objects.filter(email_verification_required=True).exists():
            raise RehearsalRefused('Existing customers unexpectedly require email verification.')
        if CustomerEmail.objects.exists() or AccountRequestLimit.objects.exists():
            raise RehearsalRefused('New account tables contain unexpected data; investigate this isolated copy.')
        call_command('check')
        print('REHEARSAL PASSED: users, credentials, grants, sessions and financial records unchanged; '
              'existing customer verification requirements false; new account tables empty.', flush=True)
    finally:
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except RehearsalRefused as error:
        print('REHEARSAL STOPPED: ' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
    except Exception:
        # DB/SMTP exception strings can contain infrastructure or credentials.
        # Keep diagnostics structural; inspect sensitive server details privately.
        print('REHEARSAL STOPPED: preflight, isolation or preservation check failed. '
              'No production target is permitted. Inspect the private environment and retained baseline.',
              file=sys.stderr, flush=True)
        raise SystemExit(1)

