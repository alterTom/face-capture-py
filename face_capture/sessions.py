import logging
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from .actions import ACTION_LABELS

log = logging.getLogger(__name__)
TERMINAL = {'passed', 'failed', 'cancelled', 'expired'}


class ServiceError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class Session:
    id: str
    token: str
    nonce: str
    actions: list
    camera_index: int
    created: float
    heartbeat: float
    status: str = 'pending_consent'
    started: float | None = None
    done: float | None = None
    preview: bytes | None = None
    photo: bytes | None = None
    error_code: str | None = None
    prompt: str = '请在浏览器授权页确认本次采集'
    action: str | None = None
    capture_block_reason: str | None = None
    completed: list = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    worker_active: bool = False
    thread: threading.Thread | None = None


class SessionManager:
    def __init__(self, worker=None, clock=time.monotonic):
        self.worker = worker
        self.clock = clock
        self.lock = threading.RLock()
        self.sessions = {}

    def create(self, actions=None, camera_index=0, require_consent=True):
        self.sweep()
        if actions is None:
            actions = ['blink', secrets.choice(['turn_left', 'turn_right'])]
        if not 1 <= len(actions) <= 4 or any(a not in ACTION_LABELS for a in actions):
            raise ServiceError('INVALID_ACTIONS', '请选择 1 至 4 个受支持的动作', 422)
        with self.lock:
            if any(s.status not in TERMINAL or s.worker_active for s in self.sessions.values()):
                raise ServiceError('CAMERA_BUSY', '已有采集任务，请完成或取消后重试', 409)
            if len(self.sessions) >= 32:
                raise ServiceError('TOO_MANY_SESSIONS', '任务过多，请稍后重试', 429)
            now = self.clock()
            s = Session(uuid.uuid4().hex, secrets.token_urlsafe(32), secrets.token_urlsafe(32),
                        list(actions), camera_index, now, now)
            self.sessions[s.id] = s
            log.info('Session %s created, actions=%s', s.id, s.actions)
            if not require_consent:
                self.approve(s.id, s.nonce)
            return {'sessionId': s.id, 'token': s.token, 'status': s.status,
                    'actions': s.actions,
                    'authorizeUrl': '/authorize?session=' + s.id if require_consent else None}

    def _get(self, sid):
        s = self.sessions.get(sid)
        if s is None:
            raise ServiceError('SESSION_NOT_FOUND', '任务不存在或已过期', 404)
        return s

    def authenticate(self, sid, token):
        with self.lock:
            s = self._get(sid)
            if not token or not secrets.compare_digest(s.token, token):
                raise ServiceError('UNAUTHORIZED', '采集会话令牌无效', 401)
            return s

    def consent_info(self, sid):
        self.sweep()
        with self.lock:
            s = self._get(sid)
            if s.status != 'pending_consent':
                raise ServiceError('NOT_PENDING', '该任务已处理或过期', 409)
            return {'nonce': s.nonce, 'actions': s.actions, 'cameraIndex': s.camera_index}

    def approve(self, sid, nonce):
        self.sweep()
        with self.lock:
            s = self._get(sid)
            if s.status != 'pending_consent' or not secrets.compare_digest(s.nonce, nonce):
                raise ServiceError('INVALID_CONSENT', '授权已过期或无效', 403)
            s.status = 'running'
            s.started = s.heartbeat = self.clock()
            s.prompt = '正在初始化模型和摄像头'
            s.nonce = ''
            s.worker_active = True
            s.thread = threading.Thread(target=self._run, args=(s,), daemon=True, name='capture')
            s.thread.start()
            log.info('Session %s approved', sid)

    def deny(self, sid, nonce):
        with self.lock:
            s = self._get(sid)
            if s.status != 'pending_consent' or not secrets.compare_digest(s.nonce, nonce):
                raise ServiceError('INVALID_CONSENT', '授权已过期或无效', 403)
            self._stop(s, 'cancelled', 'USER_DENIED', '本次采集已拒绝')

    def _run(self, s):
        try:
            if self.worker is None:
                from .isolation import run_isolated
                run_isolated(s, self)
            else:
                self.worker(s, self)
        except ServiceError as exc:
            self.fail(s.id, exc.code, exc.message)
        except Exception:
            log.exception('Capture failed for session %s', s.id)
            self.fail(s.id, 'CAPTURE_ERROR', '采集异常，请查看本地日志后重试')
        finally:
            with self.lock:
                if s.status == 'running':
                    self._stop(s, 'failed', 'CAPTURE_INTERRUPTED', '采集已中断')
                s.worker_active = False
                s.preview = None
                log.info('Session %s worker released', s.id)

    def publish(self, sid, preview=None, progress=None):
        with self.lock:
            s = self._get(sid)
            if s.status != 'running': return False
            if preview is not None: s.preview = preview
            if progress:
                if s.prompt != progress.get('prompt'):
                    log.info('Session %s progress=%s', sid, progress.get('prompt'))
                s.prompt = progress.get('prompt', s.prompt)
                s.action = progress.get('action')
                s.capture_block_reason = progress.get('captureBlockReason')
                s.completed = list(progress.get('completedActions', s.completed))
            return True

    def finish(self, sid, photo):
        with self.lock:
            s = self._get(sid)
            if s.status != 'running' or s.cancel.is_set(): return
            s.photo = photo
            s.status, s.done, s.prompt = 'passed', self.clock(), '采集成功'
            s.completed = list(s.actions)
            s.action = s.capture_block_reason = None
            s.preview = None
            log.info('Session %s passed, jpeg_bytes=%d', sid, len(photo))

    def _stop(self, s, status, code, message):
        s.status, s.error_code, s.prompt, s.done = status, code, message, self.clock()
        s.cancel.set()
        s.preview = s.photo = None
        s.nonce = ''
        log.info('Session %s stopped: %s', s.id, code)

    def fail(self, sid, code, message):
        with self.lock:
            s = self._get(sid)
            if s.status == 'running': self._stop(s, 'failed', code, message)

    def cancel_session(self, sid, token):
        with self.lock:
            s = self.authenticate(sid, token)
            self._stop(s, 'cancelled', 'CANCELLED', '采集已取消')

    def snapshot(self, sid, token):
        self.sweep()
        with self.lock:
            s = self.authenticate(sid, token)
            if s.status == 'running': s.heartbeat = self.clock()
            return {'sessionId': s.id, 'status': s.status, 'actions': s.actions,
                    'completedActions': list(s.completed), 'action': s.action,
                    'prompt': s.prompt, 'errorCode': s.error_code,
                    'captureBlockReason': s.capture_block_reason,
                    'remainingSeconds': max(0, round(60 - (self.clock() - (s.started or s.created))))}

    def image(self, sid, token, kind):
        self.sweep()
        with self.lock:
            s = self.authenticate(sid, token)
            blob = s.photo if kind == 'photo' else s.preview
            if blob is None:
                raise ServiceError('IMAGE_NOT_READY', '照片或预览尚未就绪', 409)
            return blob

    def sweep(self):
        with self.lock:
            now = self.clock()
            for sid, s in list(self.sessions.items()):
                if s.status == 'pending_consent' and now - s.created > 60:
                    self._stop(s, 'expired', 'CONSENT_TIMEOUT', '等待确认超时')
                elif s.status == 'running':
                    if now - s.heartbeat > 15:
                        self._stop(s, 'expired', 'CLIENT_DISCONNECTED', '浏览器已断开，采集已停止')
                    elif now - s.started > 60:
                        self._stop(s, 'expired', 'SESSION_TIMEOUT', '采集超时，请重试')
                if s.done is not None and now - s.done > 120 and not s.worker_active:
                    s.photo = s.preview = None
                    del self.sessions[sid]

    def close(self):
        with self.lock:
            sessions = list(self.sessions.values())
            for s in sessions:
                if s.status not in TERMINAL:
                    self._stop(s, 'cancelled', 'SHUTDOWN', '服务正在退出')
                s.photo = s.preview = None
        for s in sessions:
            if s.thread: s.thread.join(timeout=7)
