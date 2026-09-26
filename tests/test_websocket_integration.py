"""Real TCP/WebSocket transport with synthetic photos; no camera access."""
import json
from pathlib import Path
import shutil
import subprocess
import time
import unittest
from face_capture.backend import BackendService
from face_capture.sessions import SessionManager


class WebSocketIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required for SDK transport test')
    def test_real_sdk_receives_push_and_downloads_photo(self):
        def worker(session, manager):
            manager.publish(session.id, preview=b'preview')
            if not session.cancel.wait(.5):
                manager.finish(session.id, b'final-jpeg')
        backend = BackendService(port=0, manager=SessionManager(worker=worker))
        backend.start()
        try:
            deadline = time.monotonic() + 5
            while not backend.ready and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(backend.ready, backend.error)
            script = r'''
const fs = require('node:fs');
global.window = {};
global.location = {origin: process.argv[1]};
const nativeFetch = global.fetch;
const NativeSocket = global.WebSocket;
global.WebSocket = class extends NativeSocket {
  constructor(url) {
    super(url);
    this.addEventListener('message', event => console.error('WS message', typeof event.data === 'string' ? event.data : 'binary'));
    this.addEventListener('error', event => console.error('WS error', event.error));
    this.addEventListener('close', event => console.error('WS close', event.code, event.reason));
  }
};
let polls = 0, previews = 0;
global.fetch = (url, options) => {
  if ((!options.method || options.method === 'GET') && /\/capture\/sessions\/[^/]+(\/preview)?$/.test(url)) polls++;
  return nativeFetch(url, options);
};
eval(fs.readFileSync('web/capture-sdk.js', 'utf8'));
(async () => {
  const client = new window.FaceCaptureClient(process.argv[1]);
  const photo = await client.capture({requireConsent:false,actions:['blink'],onPreview:()=>previews++});
  console.log(JSON.stringify({polls, previews, photo:await photo.text(), active:client.active}));
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
            result = subprocess.run([shutil.which('node'), '-e', script, backend.url],
                                    cwd=Path(__file__).resolve().parents[1],
                                    capture_output=True, text=True, encoding='utf-8', timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['polls'], 0, result.stderr)
            self.assertGreater(data['previews'], 0)
            self.assertEqual(data['photo'], 'final-jpeg')
            self.assertIsNone(data['active'])
        finally:
            backend.request_stop()
            backend.join(5)
