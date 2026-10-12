import sys
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent / 'control'))
from diagnose import DIAGNOSTICS, DiagnosticCloud, redact
from protocol import ControlError

class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        DIAGNOSTICS.clear()

    def test_credentials_and_capabilities_are_removed(self):
        text = 'Authorization: Bearer testing-secret\nhttps://host/s/abcdefghijklmnopqrstuvwxyz0123456/working/dns ghp_abcdef github_pat_123456'
        out = redact(text, 'testing-secret')
        for value in ('testing-secret', 'abcdefghijklmnopqrstuvwxyz0123456', 'ghp_abcdef', 'github_pat_123456'):
            self.assertNotIn(value, out)

    def test_output_is_bounded(self):
        self.assertLessEqual(len(redact('a'*9000)), 6000)

    @patch('diagnose.subprocess.run')
    def test_ssh_failure_is_encrypted_diagnostic_only(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '', 'connection refused https://host/s/abcdefghijklmnopqrstuvwxyz0123456/')
        cloud = DiagnosticCloud('test-token')
        with self.assertRaisesRegex(ControlError, 'CODESPACE_SSH_FAILED'):
            cloud.gh(['ssh', '-c', 'test-name'])
        self.assertEqual(DIAGNOSTICS[-1]['operation'], 'ssh')
        self.assertIn('connection refused', DIAGNOSTICS[-1]['stderr'])
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz', str(DIAGNOSTICS))

    @patch('diagnose.subprocess.run')
    def test_success_does_not_log_session_output(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, 'private-session-data', '')
        self.assertEqual(DiagnosticCloud('test-token').gh(['ssh']), 'private-session-data')
        self.assertNotIn('private-session-data', str(DIAGNOSTICS))

    @patch('diagnose.subprocess.run')
    def test_port_failure_is_distinct(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '', 'denied')
        with self.assertRaisesRegex(ControlError, 'CODESPACE_PORT_FAILED'):
            DiagnosticCloud('test-token').gh(['ports', 'visibility'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
