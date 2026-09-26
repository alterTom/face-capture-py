import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from face_capture.runtime import InstanceGuard, ControlEvents, signal_event, configure_mpl_cache


@unittest.skipUnless(os.name == 'nt', 'Windows single-instance guard')
class RuntimeTests(unittest.TestCase):
    def test_packaged_process_uses_persistent_font_cache(self):
        cache = Path('test-output') / 'cache-test'
        with patch('sys.frozen', True, create=True), patch.dict(os.environ, {'MPLCONFIGDIR': 'temporary-hook-dir'}):
            configure_mpl_cache(cache)
            self.assertEqual(os.environ['MPLCONFIGDIR'], str(cache))

    def test_show_notification_is_consumed_once_and_stop_remains_set(self):
        stop = 'FaceCaptureTestStop-' + str(os.getpid())
        show = 'FaceCaptureTestShow-' + str(os.getpid())
        with ControlEvents(stop, show) as events:
            self.assertEqual(events.poll(), (False, False))
            self.assertTrue(signal_event(show, timeout=0))
            self.assertEqual(events.poll(), (False, True))
            self.assertEqual(events.poll(), (False, False))
            self.assertTrue(signal_event(stop, timeout=0))
            self.assertEqual(events.poll(), (True, False))
            self.assertEqual(events.poll(), (True, False))

    def test_duplicate_instance_does_not_acquire_guard(self):
        name = 'FaceCaptureTest-' + str(os.getpid())
        with InstanceGuard(name) as first:
            self.assertTrue(first.acquired)
            with InstanceGuard(name) as second:
                self.assertFalse(second.acquired)
        with InstanceGuard(name) as again:
            self.assertTrue(again.acquired)
