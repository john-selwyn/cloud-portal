"""Install a guarded Hestia 1.10.5 Web Domains card. Run as root on Hestia."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import stat
import re

ROOT = Path('/usr/local/hestia')
SOURCE = Path(__file__).resolve().parent
DEST = Path('/usr/local/share/ict-hosting-ui')
HOOK = Path('/etc/hestiacp/hooks/post_install.sh')
MARKER = "<?php /* ICT-CONNECTIONS */ require __DIR__ . '/../includes/ict-connections.php'; ?>\n"
UPSTREAM_BLOB = '9e91e92f97ac9444181e653e463e3ee254954a33'
HOOK_BLOCK = '\n# BEGIN ICT-CONNECTIONS\n/usr/bin/python3 /usr/local/share/ict-hosting-ui/install.py --apply\n# END ICT-CONNECTIONS\n'


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def atomic_write(path, data):
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.ict-connections-')
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--remove', action='store_true')
    args = parser.parse_args(argv)
    if args.apply and args.remove:
        parser.error('Choose apply or remove, not both')
    target = ROOT / 'web/templates/pages/list_web.php'
    text = target.read_bytes()
    clean = text.removeprefix(MARKER.encode())
    # Never overwrite an unfamiliar template, including a changed upstream update.
    if git_blob(clean) != UPSTREAM_BLOB:
        raise SystemExit('STOP: Web Domains template differs from reviewed Hestia 1.10.5. Review before installation.')
    if not args.apply and not args.remove:
        print('CHECK PASSED: reviewed template found; no files changed. Use --apply to install.')
        return
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the Hestia server.')
    if args.remove:
        hook = None
        if HOOK.exists():
            hook = HOOK.read_text()
            if ('ICT-CONNECTIONS' in hook and HOOK_BLOCK not in hook) or hook.count(HOOK_BLOCK) > 1:
                raise SystemExit('STOP: unfamiliar hook blocks; review manually.')
        atomic_write(target, clean)
        if hook is not None:
            atomic_write(HOOK, hook.replace(HOOK_BLOCK, '').encode())
        print('REMOVED: card include and owned update-hook block. Backups/assets retained.')
        return
    php = ROOT / 'php/bin/php'
    if not php.is_file():
        raise SystemExit('STOP: Hestia PHP interpreter not found.')
    subprocess.run([str(php), '-l', str(SOURCE / 'ict-connections.php')], check=True)
    config = json.loads((SOURCE / 'access.json').read_text())
    if not (1 <= int(config['port']) <= 65535) or not config['host'] or not config['fingerprint']:
        raise SystemExit('STOP: invalid endpoint configuration.')
    old_hook = HOOK.read_text() if HOOK.exists() else '#!/bin/sh\n'
    if 'ICT-CONNECTIONS' in old_hook and HOOK_BLOCK not in old_hook:
        raise SystemExit('STOP: unfamiliar existing hook block.')
    if not old_hook.startswith(('#!/bin/sh', '#!/bin/bash', '#!/usr/bin/env bash')):
        raise SystemExit('STOP: review existing update hook interpreter.')
    if re.search(r'^\s*(exit|exec)\b', old_hook, re.MULTILINE):
        raise SystemExit('STOP: existing hook may exit before the appended block; review integration.')
    DEST.mkdir(parents=True, exist_ok=True)
    backup = DEST / 'original-list_web.php'
    if not backup.exists():
        backup.write_bytes(clean)
    if HOOK.exists() and not (DEST / 'original-post_install.sh').exists():
        shutil.copy2(HOOK, DEST / 'original-post_install.sh')
    for name in ('install.py', 'ict-connections.php', 'ict-connections.css', 'ict-connections.js', 'access.json'):
        if (SOURCE / name).resolve() != (DEST / name).resolve():
            shutil.copyfile(SOURCE / name, DEST / name)
        (DEST / name).chmod(0o644)
    for relative, name in (
        ('web/templates/includes/ict-connections.php', 'ict-connections.php'),
        ('web/css/custom/ict-connections.css', 'ict-connections.css'),
        ('web/js/custom/ict-connections.js', 'ict-connections.js'),
    ):
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEST / name, path)
        path.chmod(0o644)
    atomic_write(target, MARKER.encode() + clean)
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    if HOOK_BLOCK not in old_hook:
        atomic_write(HOOK, (old_hook + HOOK_BLOCK).encode())
    HOOK.chmod(0o755)
    print('INSTALLED: customer connection card. Existing hook preserved; no service restart performed.')


if __name__ == '__main__':
    main()
