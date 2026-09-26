"""Only for browser verification, never included in the installed program.

Runs production capture pipeline with synthetic frames/action samples on port 18766.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from face_capture.actions import Sample
from face_capture.api import create_app
from face_capture.sessions import SessionManager
from face_capture.vision import capture


class FixtureCamera:
    def isOpened(self): return True
    def set(self, *args): pass
    def release(self): pass
    def read(self):
        time.sleep(.04)
        frame = np.full((480, 640, 3), (70, 100, 150), dtype=np.uint8)
        cv2.putText(frame, 'SIMULATED TEST FRAME', (75, 230), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        return True, frame


class FixtureAnalyzer:
    def __enter__(self): self.started = time.monotonic(); return self
    def __exit__(self, *args): pass
    def analyze(self, frame, timestamp):
        elapsed = time.monotonic() - self.started
        return Sample(blink=.9 if .7 < elapsed < .95 else 0)


def fixture_worker(s, m):
    capture(s, m, camera_factory=lambda index: FixtureCamera(), analyzer_factory=FixtureAnalyzer)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(create_app(SessionManager(worker=fixture_worker)), host='127.0.0.1', port=18766, access_log=False)
