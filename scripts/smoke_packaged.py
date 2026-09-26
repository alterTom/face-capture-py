"""Exercise the actual packaged background executable without installing it."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'dist/FaceCapture/FaceCapture.exe'
BASE = 'http://127.0.0.1:18765'
runtime = ROOT / 'test-output/packaged-runtime'
runtime.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, FACE_CAPTURE_DATA_DIR=str(runtime))
report = {}


def request(path, data=None, token=None, method=None, consent=False):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    if consent: headers.update({'Origin': BASE, 'Sec-Fetch-Site': 'same-origin'})
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=payload, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.load(response)


if __name__ == '__main__':
    proc = subprocess.Popen([str(EXE)], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        for _ in range(100):
            if proc.poll() is not None: raise RuntimeError('Packaged service exited on startup')
            try:
                health = request('/health')
                break
            except (OSError, urllib.error.URLError): time.sleep(.1)
        else: raise RuntimeError('Service startup timed out')
        assert health['service'] == 'face-capture' and health['modelReady']
        report['health'] = health
        duplicate = subprocess.run([str(EXE)], env=env, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        assert duplicate.returncode == 0 and proc.poll() is None
        report['duplicateInstanceExits'] = True
        session = request('/capture/sessions', {'actions': ['blink'], 'cameraIndex': 9})
        sid, token = session['sessionId'], session['token']
        info = request('/consent/' + sid, consent=True)
        request('/consent/' + sid, {'nonce': info['nonce']}, consent=True)
        # Only use index 9 to exercise the error path, do not capture a person's photo.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = request('/capture/sessions/' + sid, token=token)
            if state['status'] in ('failed', 'passed', 'expired'): break
            time.sleep(.15)
        assert state['errorCode'] == 'CAMERA_UNAVAILABLE', state
        report['packagedCameraSubprocess'] = state['errorCode']
        request('/capture/sessions/' + sid, token=token, method='DELETE')
        stopped = subprocess.run([str(EXE), '--stop'], env=env, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        assert stopped.returncode == 0
        proc.wait(timeout=10)
        assert proc.returncode == 0
        report['gracefulShutdown'] = True
        report['ok'] = True
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        (ROOT / 'test-output/packaged-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
