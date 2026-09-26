import json
import socket
import time
import unittest
import urllib.request
from face_capture.backend import BackendService
from face_capture.sessions import SessionManager


class BackendTests(unittest.TestCase):
    def test_http_service_runs_and_shutdown_releases_active_session_and_port(self):
        manager = SessionManager(worker=lambda s, m: s.cancel.wait(10))
        backend = BackendService(port=0, manager=manager)
        backend.start()
        try:
            deadline = time.monotonic() + 5
            while not backend.ready and time.monotonic() < deadline: time.sleep(.02)
            self.assertTrue(backend.ready, backend.error)
            with urllib.request.urlopen(backend.url + '/health', timeout=2) as response:
                self.assertEqual(json.load(response)['service'], 'face-capture')
            info = manager.create(['blink'])
            session = manager.sessions[info['sessionId']]
            manager.approve(session.id, session.nonce)
            backend.request_stop()
            backend.join(5)
            self.assertFalse(backend.alive)
            self.assertTrue(session.cancel.is_set())
            self.assertFalse(session.worker_active)
            with socket.socket() as connection:
                self.assertNotEqual(connection.connect_ex(('127.0.0.1', backend.port)), 0)
        finally:
            backend.request_stop()
            backend.join(5)

    def test_occupied_port_is_reported_without_killing_desktop_process(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            backend = BackendService(port=occupied.getsockname()[1])
            backend.start()
            backend.join(5)
            self.assertFalse(backend.ready)
            self.assertFalse(backend.alive)
            self.assertIn('端口', backend.error)
