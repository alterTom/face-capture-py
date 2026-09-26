import functools
import time
import unittest
from face_capture.isolation import run_isolated
from face_capture.sessions import SessionManager


def blocked_camera(sid, actions, index, cancel, messages):
    # Simulate a driver call that never checks cancellation.
    messages.put(('progress', {'prompt': 'blocked read'}, b'preview'))
    time.sleep(120)


def returning_camera(sid, actions, index, cancel, messages):
    messages.put(('success', b'jpeg-data'))


class IsolationTests(unittest.TestCase):
    def test_cancel_terminates_blocked_driver_and_allows_next_session(self):
        manager = SessionManager(worker=functools.partial(run_isolated, target=blocked_camera))
        try:
            info = manager.create(['blink'])
            s = manager.sessions[info['sessionId']]
            manager.approve(s.id, s.nonce)
            deadline = time.monotonic() + 8
            while s.prompt != 'blocked read' and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(s.prompt, 'blocked read')
            manager.cancel_session(s.id, s.token)
            s.thread.join(5)
            self.assertFalse(s.worker_active)
            self.assertIsNone(s.preview)
            self.assertEqual(manager.create(['blink'])['status'], 'pending_consent')
        finally: manager.close()

    def test_child_process_jpeg_reaches_parent_session(self):
        manager = SessionManager(worker=functools.partial(run_isolated, target=returning_camera))
        try:
            info = manager.create(['blink'])
            s = manager.sessions[info['sessionId']]
            manager.approve(s.id, s.nonce)
            s.thread.join(8)
            self.assertEqual(s.status, 'passed')
            self.assertEqual(manager.image(s.id, s.token, 'photo'), b'jpeg-data')
        finally: manager.close()
