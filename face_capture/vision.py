"""Camera ownership and local Face Landmarker inference. No desktop UI."""
import logging
import math
import time
import cv2
import numpy as np
from .actions import ActionTracker, Sample
from .paths import resource_path
from .sessions import ServiceError

log = logging.getLogger(__name__)


class FaceAnalyzer:
    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        model = resource_path('models/face_landmarker.task')
        if not model.is_file():
            raise ServiceError('MODEL_MISSING', '人脸模型缺失，请重新安装程序', 503)
        self.mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO, num_faces=2,
            min_face_detection_confidence=.6, min_face_presence_confidence=.6,
            min_tracking_confidence=.6, output_face_blendshapes=True,
            output_facial_transformation_matrixes=True)
        self.detector = vision.FaceLandmarker.create_from_options(options)

    def __enter__(self): return self
    def __exit__(self, *args): self.detector.close()

    def analyze(self, frame, timestamp_ms):
        height, width = frame.shape[:2]
        small = cv2.resize(frame, (640, max(1, round(height * 640 / width))))
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        result = self.detector.detect_for_video(image, timestamp_ms)
        faces = len(result.face_landmarks)
        if faces != 1: return Sample(faces=faces)
        landmarks = result.face_landmarks[0]
        xs, ys = [p.x for p in landmarks], [p.y for p in landmarks]
        left, right = max(0., min(xs)), min(1., max(xs))
        top, bottom = max(0., min(ys)), min(1., max(ys))
        crop = frame[int(top * height):int(bottom * height), int(left * width):int(right * width)]
        if crop.size == 0: return Sample(faces=0)
        gray = cv2.cvtColor(cv2.resize(crop, (256, 256)), cv2.COLOR_BGR2GRAY)
        blend = {c.category_name: c.score for c in result.face_blendshapes[0]}
        rotation = np.asarray(result.facial_transformation_matrixes[0])[:3, :3]
        # Remove scale before Euler extraction. Mirror only the HTML preview, not inference.
        rotation = rotation / np.linalg.norm(rotation, axis=0)
        yaw = math.degrees(math.atan2(rotation[0, 2], rotation[2, 2]))
        pitch = math.degrees(math.atan2(-rotation[1, 2], math.hypot(rotation[1, 0], rotation[1, 1])))
        roll = math.degrees(math.atan2(rotation[1, 0], rotation[1, 1]))
        return Sample(faces=1, blink=min(blend.get('eyeBlinkLeft', 0), blend.get('eyeBlinkRight', 0)),
                      eye_closed_max=max(blend.get('eyeBlinkLeft', 0), blend.get('eyeBlinkRight', 0)),
                      mouth=blend.get('jawOpen', 0), yaw=yaw, pitch=pitch, roll=roll,
                      sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
                      brightness=float(gray.mean()), size=right - left,
                      centered=.22 < (left + right) / 2 < .78 and .2 < (top + bottom) / 2 < .8)


def open_camera(index):
    camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(index, cv2.CAP_MSMF)
    return camera


def encode_jpeg(frame, quality=88):
    ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok: raise ServiceError('ENCODE_FAILED', '图片编码失败，请重试')
    return data.tobytes()


def capture(session, manager, camera_factory=open_camera, analyzer_factory=FaceAnalyzer):
    camera = None
    connected = False
    stop_reason = '采集结束'
    try:
        if session.cancel.is_set(): return
        log.info('正在连接摄像头：编号=%s，任务=%s', session.camera_index, session.id)
        camera = camera_factory(session.camera_index)
        if not camera.isOpened():
            raise ServiceError('CAMERA_UNAVAILABLE', '摄像头无法打开，请检查连接、系统相机权限及是否被其他程序占用')
        connected = True
        log.info('摄像头连接成功：编号=%s，任务=%s', session.camera_index, session.id)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        camera.set(cv2.CAP_PROP_FPS, 30)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if session.cancel.is_set(): return
        first_frame = None
        failures = 0
        while not session.cancel.is_set():
            ok, first_frame = camera.read()
            if ok and first_frame is not None:
                h, w = first_frame.shape[:2]
                preview = encode_jpeg(cv2.resize(first_frame, (640, round(h * 640 / w))), 72)
                if not manager.publish(session.id, preview=preview): return
                log.info('摄像头首帧已发送：编号=%s，任务=%s', session.camera_index, session.id)
                break
            failures += 1
            if failures >= 10:
                raise ServiceError('CAMERA_READ_FAILED', '无法读取摄像头画面，请检查设备连接')
            session.cancel.wait(.05)
        if session.cancel.is_set(): return
        with analyzer_factory() as analyzer:
            log.info('人脸模型初始化完成：编号=%s，任务=%s', session.camera_index, session.id)
            tracker = ActionTracker(session.actions, time.monotonic())
            last_stamp, last_preview, failures = -1, 0., 0
            last_quality_log = -float('inf')
            while not session.cancel.is_set():
                if first_frame is not None:
                    ok, frame = True, first_frame
                    first_frame = None
                else:
                    ok, frame = camera.read()
                if not ok or frame is None:
                    failures += 1
                    if failures >= 10:
                        raise ServiceError('CAMERA_READ_FAILED', '无法读取摄像头画面，请检查设备连接')
                    session.cancel.wait(.05)
                    continue
                failures = 0
                now = time.monotonic()
                stamp = max(last_stamp + 1, int(now * 1000))
                last_stamp = stamp
                sample = analyzer.analyze(frame, stamp)
                progress = tracker.update(sample, now)
                if progress['captureReady']:
                    manager.finish(session.id, encode_jpeg(frame, 92))
                    stop_reason = '抓拍完成'
                    log.info('Session %s captured immediately on eligible frame', session.id)
                    break
                if progress['captureBlockReason'] and now - last_quality_log >= 2:
                    log.info('Photo waiting: reason=%s yaw=%.1f pitch=%.1f roll=%.1f '
                             'eye=%.2f mouth=%.2f sharpness=%.1f brightness=%.1f',
                             progress['captureBlockReason'], sample.yaw, sample.pitch, sample.roll,
                             max(sample.blink, sample.eye_closed_max), sample.mouth,
                             sample.sharpness, sample.brightness)
                    last_quality_log = now
                preview = None
                if now - last_preview >= .1:
                    h, w = frame.shape[:2]
                    preview = encode_jpeg(cv2.resize(frame, (640, round(h * 640 / w))), 72)
                    last_preview = now
                if not manager.publish(session.id, preview=preview, progress=progress): break
                if progress['errorCode']:
                    stop_reason = progress['errorCode']
                    manager.fail(session.id, progress['errorCode'], progress['prompt'])
                    break
                session.cancel.wait(.005)
    except Exception as exc:
        stop_reason = exc.code if isinstance(exc, ServiceError) else '采集异常'
        log.exception('%s：编号=%s，任务=%s，原因=%s',
                      '摄像头采集异常' if connected else '摄像头连接失败',
                      session.camera_index, session.id, stop_reason)
        raise
    finally:
        if camera is not None:
            if session.cancel.is_set() and stop_reason == '采集结束':
                stop_reason = '任务已取消或停止'
            if connected:
                log.info('正在断开摄像头：编号=%s，任务=%s，原因=%s',
                         session.camera_index, session.id, stop_reason)
            try:
                camera.release()
            except Exception:
                log.exception('摄像头资源释放失败：编号=%s，任务=%s', session.camera_index, session.id)
                raise
            log.info('%s：编号=%s，任务=%s，原因=%s',
                     '摄像头已断开，资源已释放' if connected else '未连接的摄像头句柄已清理',
                     session.camera_index, session.id, stop_reason)
