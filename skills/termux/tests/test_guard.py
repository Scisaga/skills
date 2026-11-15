"""Safety cases for the automatic orphan-helper policy. No live process is signalled."""
import copy
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets/desktop/native'))
from session_manager import UID, may_reap, same_identity


class GuardSafety(unittest.TestCase):
    def setUp(self):
        self.record = {'pid': 987654, 'start': 12345, 'exe': '/usr/share/code/code',
                       'uid': UID, 'kind': 'code-zygote', 'root': 1234,
                       'session': 'test-session', 'tracer': 0}

    def eligible(self, record=None, current=None, **kwargs):
        return may_reap(record or self.record, current or self.record,
                        kwargs.get('root_alive', False), kwargs.get('core_alive', False),
                        kwargs.get('high_samples', 2))

    def test_known_detached_helper_after_ended_session(self):
        self.assertTrue(self.eligible())

    def test_high_cpu_in_active_desktop_is_not_terminated(self):
        self.assertFalse(self.eligible(core_alive=True))
        self.assertFalse(self.eligible(root_alive=True))

    def test_recycled_pid_is_not_terminated(self):
        current = dict(self.record, start=12346)
        self.assertFalse(self.eligible(current=current))

    def test_other_uid_is_not_terminated(self):
        current = dict(self.record, uid=UID + 1)
        self.assertFalse(self.eligible(current=current))

    def test_application_main_renderer_and_compiler_are_not_terminated(self):
        for kind in ('guest', 'xfce-session', 'proot', 'renderer', 'compiler'):
            r = dict(self.record, kind=kind)
            self.assertFalse(self.eligible(record=r, current=r), kind)

    def test_still_traced_process_is_not_terminated(self):
        self.assertFalse(self.eligible(current=dict(self.record, tracer=1234)))

    def test_single_sample_or_unregistered_process_is_not_terminated(self):
        self.assertFalse(self.eligible(high_samples=1))
        self.assertFalse(self.eligible(record=dict(self.record, session=None)))
        self.assertFalse(self.eligible(record=dict(self.record, root=None)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
