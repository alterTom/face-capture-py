import unittest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from face_capture.api import create_app
from face_capture.sessions import SessionManager


class WebSocketTests(unittest.TestCase):
    def setUp(self):
        def worker(s, m):
            while s.status == 'running' and not s.cancel.wait(.02):
                pass
        self.manager = SessionManager(worker=worker)
        self.info = self.manager.create(['blink'], require_consent=False)
        self.sid = self.info['sessionId']
        self.client = TestClient(create_app(self.manager), base_url='http://127.0.0.1')

    def tearDown(self):
        self.manager.close()

    def test_push_preview_then_terminal_and_http_photo(self):
        self.manager.publish(self.sid, preview=b'jpeg')
        with self.client.websocket_connect(f'ws://127.0.0.1/capture/sessions/{self.sid}/stream') as ws:
            ws.send_json({'type': 'auth', 'token': self.info['token']})
            self.assertEqual(ws.receive_json()['state']['status'], 'running')
            self.assertEqual(ws.receive_bytes(), b'jpeg')
            self.assertEqual(ws.receive_json()['type'], 'sync')
            self.manager.finish(self.sid, b'final')
            ws.send_json({'type': 'ack'})
            self.assertEqual(ws.receive_json()['state']['status'], 'passed')
        result = self.client.get(f'/capture/sessions/{self.sid}/photo',
                                 headers={'Authorization': 'Bearer ' + self.info['token']})
        self.assertEqual(result.content, b'final')

    def test_invalid_token_cannot_receive_photos(self):
        with self.client.websocket_connect(f'ws://127.0.0.1/capture/sessions/{self.sid}/stream') as ws:
            ws.send_json({'type': 'auth', 'token': 'wrong'})
            self.assertEqual(ws.receive_json()['errorCode'], 'UNAUTHORIZED')
            ws.send_json({'type': 'ack'})
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()

    def test_slow_consumer_gets_latest_frame_and_ack_keeps_session_alive(self):
        clock = [100.0]
        self.manager.clock = lambda: clock[0]
        session = self.manager.sessions[self.sid]
        session.started = session.heartbeat = 100.0
        self.manager.publish(self.sid, preview=b'first')
        with self.client.websocket_connect(f'ws://127.0.0.1/capture/sessions/{self.sid}/stream') as ws:
            ws.send_json({'type': 'auth', 'token': self.info['token']})
            ws.receive_json()
            self.assertEqual(ws.receive_bytes(), b'first')
            ws.receive_json()
            for index in range(3):
                self.manager.publish(self.sid, preview=str(index).encode())
            clock[0] += 10
            ws.send_json({'type': 'ack'})
            self.assertEqual(ws.receive_json()['state']['status'], 'running')
            self.assertEqual(ws.receive_bytes(), b'2')
            self.assertEqual(session.heartbeat, 110.0)
            ws.receive_json()
            self.manager.cancel_session(self.sid, self.info['token'])
            ws.send_json({'type': 'ack'})
            self.assertEqual(ws.receive_json()['state']['status'], 'cancelled')

    def test_invalid_auth_message_is_closed(self):
        with self.client.websocket_connect(f'ws://127.0.0.1/capture/sessions/{self.sid}/stream') as ws:
            ws.send_json([])
            self.assertEqual(ws.receive_json()['errorCode'], 'UNAUTHORIZED')
