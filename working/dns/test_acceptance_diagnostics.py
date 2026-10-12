import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent / 'control'))
import acceptance_diagnostics as module
import verify
from diagnose import DIAGNOSTICS
from protocol import ControlError

class AcceptanceDiagnosticTests(unittest.TestCase):
    def setUp(self):
        DIAGNOSTICS.clear()

    @patch('acceptance_diagnostics.controller.check_session')
    @patch('verify.main')
    def test_failure_never_becomes_success(self, check, validate):
        previous = verify.SESSION
        check.side_effect = ValueError('HTTPS returned HTTP 502 at https://host/s/abcdefghijklmnopqrstuvwxyz0123456/')
        with self.assertRaisesRegex(ControlError, 'PUBLIC_HTTPS_ACCEPTANCE_FAILED'):
            module.acceptance({'doh': 'private'}, 'runtime')
        self.assertEqual(verify.SESSION, previous)
        self.assertIn('HTTP 502', DIAGNOSTICS[-1]['reason'])
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz', str(DIAGNOSTICS))

    @patch('acceptance_diagnostics.controller.check_session')
    def test_only_actual_verifier_success_returns_verified(self, validate):
        def checked():
            data=json.loads(verify.SESSION.read_text()); data['deployment_verified']=True
            verify.SESSION.write_text(json.dumps(data))
        with patch('verify.main', side_effect=checked) as verifier:
            result=module.acceptance({'doh': 'private'}, 'runtime')
        verifier.assert_called_once()
        self.assertTrue(result['deployment_verified'])
        self.assertEqual(DIAGNOSTICS[-1]['kind'], 'acceptance_success')

if __name__ == '__main__':
    unittest.main(verbosity=2)
