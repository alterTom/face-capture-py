import threading
import time
import unittest
from fastapi.testclient import TestClient
from face_capture.api import create_app
from face_capture.sessions import SessionManager


class Clock:
    def __init__(self): self.value = 100.0
    def __call__(self): return self.value


def waiting_worker(session, manager):
    manager.publish(session.id, preview=b'preview', progress={'prompt': '请眨眼'})
    session.cancel.wait(2)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.manager = SessionManager(worker=waiting_worker, clock=self.clock)
        self.client = TestClient(create_app(self.manager), base_url='http://127.0.0.1:18765')

    def tearDown(self): self.manager.close()

    def create(self):
        r = self.client.post('/capture/sessions', json={'actions': ['blink']},
                             headers={'Origin': 'https://any-company.example'})
        self.assertEqual(r.status_code, 201)
        return r.json()

    def headers(self, s): return {'Authorization': 'Bearer ' + s['token']}

    def approve(self, s):
        path = '/consent/' + s['sessionId']
        nonce = self.client.get(path, headers={'Sec-Fetch-Site': 'same-origin'}).json()['nonce']
        return self.client.post(path, json={'nonce': nonce}, headers={
            'Origin': 'http://127.0.0.1:18765', 'Sec-Fetch-Site': 'same-origin'})

    def test_any_origin_allowed_but_capture_waits_for_consent(self):
        s = self.create()
        r = self.client.get('/capture/sessions/' + s['sessionId'], headers=self.headers(s))
        self.assertEqual(r.json()['status'], 'pending_consent')
        self.assertFalse(self.manager.sessions[s['sessionId']].worker_active)
        r = self.client.options('/capture/sessions', headers={
            'Origin': 'https://another.example', 'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,authorization'})
        self.assertEqual(r.headers['access-control-allow-origin'], '*')

    def test_external_site_cannot_read_or_submit_consent(self):
        s = self.create()
        path = '/consent/' + s['sessionId']
        r = self.client.get(path, headers={'Origin': 'https://external.example', 'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn('access-control-allow-origin', r.headers)
        r = self.client.post(path, json={'nonce': 'bad'}, headers={'Origin': 'https://external.example'})
        self.assertEqual(r.status_code, 403)

    def test_direct_capture_starts_without_consent_and_still_requires_token(self):
        started = threading.Event()
        def direct_worker(session, manager):
            started.set()
            manager.finish(session.id, b'jpeg-direct')
        self.manager.worker = direct_worker
        r = self.client.post('/capture/sessions', json={
            'actions': ['mouth'], 'requireConsent': False},
            headers={'Origin': 'https://business.example'})
        self.assertEqual(r.status_code, 201)
        s = r.json()
        self.assertTrue(started.wait(1))
        self.assertIsNone(s['authorizeUrl'])
        path = '/capture/sessions/' + s['sessionId'] + '/photo'
        self.assertEqual(self.client.get(path).status_code, 401)
        for _ in range(100):
            photo = self.client.get(path, headers=self.headers(s))
            if photo.status_code == 200: break
            time.sleep(.01)
        self.assertEqual(photo.content, b'jpeg-direct')

    def test_token_is_required_for_images_and_status(self):
        s = self.create()
        for suffix in ['', '/preview', '/photo']:
            r = self.client.get('/capture/sessions/' + s['sessionId'] + suffix)
            self.assertEqual(r.status_code, 401)
        self.assertEqual(self.approve(s).status_code, 200)
        r = self.client.get('/capture/sessions/' + s['sessionId'] + '/photo', headers=self.headers(s))
        self.assertEqual(r.status_code, 409)

    def test_parallel_capture_rejected_and_cancel_releases_slot(self):
        s = self.create()
        self.assertEqual(self.approve(s).status_code, 200)
        r = self.client.post('/capture/sessions', json={})
        self.assertEqual(r.status_code, 409)
        self.client.delete('/capture/sessions/' + s['sessionId'], headers=self.headers(s))
        for _ in range(100):
            if not self.manager.sessions[s['sessionId']].worker_active: break
            time.sleep(.01)
        self.assertEqual(self.client.post('/capture/sessions', json={}).status_code, 201)

    def test_heartbeat_expiry_cancels_and_clears_preview(self):
        s = self.create()
        self.approve(s)
        self.clock.value += 16
        self.manager.sweep()
        r = self.client.get('/capture/sessions/' + s['sessionId'], headers=self.headers(s))
        self.assertEqual(r.json()['errorCode'], 'CLIENT_DISCONNECTED')
        self.assertIsNone(self.manager.sessions[s['sessionId']].preview)

    def test_unapproved_task_expires(self):
        s = self.create()
        self.clock.value += 61
        self.manager.sweep()
        self.assertEqual(self.manager.sessions[s['sessionId']].status, 'expired')

    def test_success_jpeg_then_result_expiry(self):
        def success(session, manager): manager.finish(session.id, photo=b'\xff\xd8image\xff\xd9')
        self.manager.worker = success
        s = self.create()
        self.approve(s)
        for _ in range(100):
            r = self.client.get('/capture/sessions/' + s['sessionId'] + '/photo', headers=self.headers(s))
            if r.status_code == 200: break
            time.sleep(.01)
        self.assertEqual(r.content, b'\xff\xd8image\xff\xd9')
        self.assertEqual(r.headers['content-type'], 'image/jpeg')
        self.assertEqual(r.headers['cache-control'], 'no-store')
        self.clock.value += 121
        self.manager.sweep()
        self.assertEqual(self.client.get('/capture/sessions/' + s['sessionId'], headers=self.headers(s)).status_code, 404)

    def test_invalid_actions_and_rebinding_host_rejected(self):
        for actions in [[], ['unknown'], ['blink'] * 6]:
            self.assertEqual(self.client.post('/capture/sessions', json={'actions': actions}).status_code, 422)
        self.assertEqual(self.client.get('/health', headers={'Host': 'evil.example'}).status_code, 400)

    def test_camera_error_visible_without_traceback_or_token(self):
        def fail(session, manager): raise RuntimeError('private internal details')
        self.manager.worker = fail
        s = self.create()
        self.approve(s)
        for _ in range(100):
            r = self.client.get('/capture/sessions/' + s['sessionId'], headers=self.headers(s))
            if r.json()['status'] == 'failed': break
            time.sleep(.01)
        self.assertEqual(r.json()['errorCode'], 'CAPTURE_ERROR')
        self.assertNotIn('private internal', r.text)
        self.assertNotIn(s['token'], r.text)
