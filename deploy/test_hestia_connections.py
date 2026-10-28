"""Filesystem rehearsal: no system paths or Hestia services are modified."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parent / 'hestia-connections/install.py'
spec = importlib.util.spec_from_file_location('hestia_connections_install', SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.hestia = root / 'hestia'
        self.dest = root / 'installed'
        self.hook = root / 'hooks/post_install.sh'
        self.target = self.hestia / 'web/templates/pages/list_web.php'
        self.target.parent.mkdir(parents=True)
        self.original = b'<!-- Reviewed template fixture -->\n'
        self.target.write_bytes(self.original)
        php = self.hestia / 'php/bin/php'
        php.parent.mkdir(parents=True)
        php.write_text('fixture')
        self.hook.parent.mkdir()
        self.hook.write_text('#!/bin/sh\necho existing-hook\n')
        for name, value in [('ROOT', self.hestia), ('DEST', self.dest), ('HOOK', self.hook),
                            ('UPSTREAM_BLOB', installer.git_blob(self.original))]:
            patcher = patch.object(installer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(installer.os, 'geteuid', return_value=0, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(installer.subprocess, 'run')
        self.lint = patcher.start()
        self.addCleanup(patcher.stop)

    def test_check_changes_nothing(self):
        installer.main([])
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertFalse(self.dest.exists())

    def test_apply_is_idempotent_preserves_hook_and_backup_and_removes_cleanly(self):
        installer.main(['--apply'])
        installer.main(['--apply'])
        self.assertEqual(self.target.read_bytes(), installer.MARKER.encode() + self.original)
        self.assertEqual((self.dest / 'original-list_web.php').read_bytes(), self.original)
        self.assertEqual(self.hook.read_text().count(installer.HOOK_BLOCK), 1)
        self.assertIn('echo existing-hook', self.hook.read_text())
        self.lint.assert_called()
        installer.main(['--remove'])
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.hook.read_text(), '#!/bin/sh\necho existing-hook\n')

    def test_refuses_changed_upstream_before_writing(self):
        self.target.write_bytes(b'new upstream or custom template')
        with self.assertRaises(SystemExit):
            installer.main(['--apply'])
        self.assertFalse(self.dest.exists())

    def test_refuses_hook_that_exits_early(self):
        self.hook.write_text('#!/bin/sh\nexit 0\n')
        with self.assertRaises(SystemExit):
            installer.main(['--apply'])
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_failed_php_lint_leaves_template_unchanged(self):
        self.lint.side_effect = RuntimeError('lint failed')
        with self.assertRaises(RuntimeError):
            installer.main(['--apply'])
        self.assertEqual(self.target.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
