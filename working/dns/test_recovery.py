import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent / 'control'))
from recover_runtime import LEGACY, candidates, require_stopped_legacy, small_machine
from protocol import ControlError, REPO, TAG, select

class RecoveryTests(unittest.TestCase):
    def item(self, name=LEGACY, state='Shutdown'):
        return {'name': name, 'state': state, 'repository': {'full_name': REPO}}

    def test_only_the_confirmed_legacy_is_excluded(self):
        old, other = self.item(), self.item('new-runtime')
        self.assertEqual(candidates([old, other]), [other])
        self.assertEqual(old['name'], LEGACY)

    def test_running_original_is_not_touched(self):
        with self.assertRaises(ControlError):
            require_stopped_legacy(self.item(state='Available'))

    def test_wrong_original_is_not_touched(self):
        with self.assertRaises(ControlError):
            require_stopped_legacy(self.item('another-runtime'))
        require_stopped_legacy(self.item())

    def test_large_machine_is_not_selected(self):
        with self.assertRaises(ControlError):
            small_machine([{'name': 'large', 'cpus': 4}])
        self.assertEqual(small_machine([{'name': 'small', 'cpus': 2}, {'name': 'large', 'cpus': 8}]), 'small')

    def test_existing_replacement_is_reused(self):
        new = self.item('new-runtime'); new['display_name'] = TAG + '1791788000'
        self.assertIs(select(candidates([self.item(), new])), new)

if __name__ == '__main__':
    unittest.main(verbosity=2)
