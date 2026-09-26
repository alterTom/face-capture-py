import unittest
from types import SimpleNamespace
from pathlib import Path
import numpy as np
from face_capture.vision import FaceAnalyzer, capture
from face_capture.sessions import SessionManager
from face_capture.actions import Sample
from unittest.mock import patch
import cv2


class VisionTests(unittest.TestCase):
    def test_first_preview_is_available_before_model_initialization(self):
        class Camera:
            reads = 0
            released = False
            def isOpened(self): return True
            def set(self, *args): pass
            def read(self):
                self.reads += 1
                return True, np.full((48, 64, 3), 120, dtype=np.uint8)
            def release(self): self.released = True

        camera = Camera()
        manager = SessionManager()
        info = manager.create(['blink'])
        session = manager.sessions[info['sessionId']]
        session.status = 'running'
        session.started = manager.clock()

        class Analyzer:
            def __init__(self):
                preview = manager.image(session.id, session.token, 'preview')
                self_preview = cv2.imdecode(np.frombuffer(preview, np.uint8), cv2.IMREAD_COLOR)
                assert self_preview is not None
                assert camera.reads == 1
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def analyze(self, frame, stamp):
                session.cancel.set()
                return Sample(faces=0)

        try:
            capture(session, manager, camera_factory=lambda i: camera, analyzer_factory=Analyzer)
            self.assertTrue(camera.released)
        finally:
            manager.close()

    def test_capture_returns_final_action_frame_without_reading_more_frames(self):
        class Camera:
            index = -1
            released = False
            def isOpened(self): return True
            def set(self, *args): pass
            def release(self): self.released = True
            def read(self):
                self.index += 1
                if self.index > 8:
                    raise AssertionError('capture requested extra frames after final valid return')
                return True, np.full((48, 64, 3), 100 + self.index, dtype=np.uint8)
        camera = Camera()
        class Analyzer:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def analyze(self, frame, stamp):
                return Sample(blink=.9 if camera.index in (4, 5) else 0)
        manager = SessionManager()
        try:
            info = manager.create(['blink'])
            session = manager.sessions[info['sessionId']]
            session.status = 'running'
            timestamps = iter([0] + [i / 10 for i in range(9)])
            with patch('face_capture.vision.time.monotonic', side_effect=lambda: next(timestamps)):
                capture(session, manager, camera_factory=lambda i: camera, analyzer_factory=Analyzer)
            self.assertEqual(session.status, 'passed')
            image = cv2.imdecode(np.frombuffer(session.photo, np.uint8), cv2.IMREAD_COLOR)
            self.assertEqual(int(image.mean()), 108)
            self.assertTrue(camera.released)
        finally: manager.close()

    def test_landmarker_preserves_single_eye_closure_for_photo_quality(self):
        analyzer = object.__new__(FaceAnalyzer)
        analyzer.mp = SimpleNamespace(Image=lambda **kwargs: kwargs,
                                      ImageFormat=SimpleNamespace(SRGB=1))
        result = SimpleNamespace(
            face_landmarks=[[SimpleNamespace(x=.3, y=.2), SimpleNamespace(x=.7, y=.8)]],
            face_blendshapes=[[SimpleNamespace(category_name='eyeBlinkLeft', score=.99),
                              SimpleNamespace(category_name='eyeBlinkRight', score=.01)]],
            facial_transformation_matrixes=[np.eye(4)])
        analyzer.detector = SimpleNamespace(detect_for_video=lambda image, timestamp: result)
        sample = analyzer.analyze(np.full((480, 640, 3), 120, dtype=np.uint8), 1)
        self.assertEqual(sample.blink, .01)
        self.assertEqual(sample.eye_closed_max, .99)

    def test_model_loads_offline_and_blank_frame_has_no_face(self):
        with FaceAnalyzer() as analyzer:
            sample = analyzer.analyze(np.zeros((480, 640, 3), dtype=np.uint8), 1000)
        self.assertEqual(sample.faces, 0)

    def test_camera_open_failure_reports_actionable_code_and_releases(self):
        class ClosedCamera:
            released = False
            def isOpened(self): return False
            def release(self): self.released = True
        camera = ClosedCamera()
        manager = SessionManager(worker=lambda s, m: capture(s, m, camera_factory=lambda i: camera))
        try:
            data = manager.create(['blink'])
            s = manager.sessions[data['sessionId']]
            manager.approve(s.id, s.nonce)
            s.thread.join(20)
            self.assertEqual(s.error_code, 'CAMERA_UNAVAILABLE')
            self.assertTrue(camera.released)
        finally: manager.close()
