"""HTTP service lifecycle; independent of the desktop toolkit."""
import logging
import socket
import threading
from .sessions import SessionManager

log = logging.getLogger(__name__)


class BackendService:
    def __init__(self, port=18765, manager=None):
        self.port = port
        self.manager = manager or SessionManager()
        self.server = None
        self.thread = None
        self.error = None
        self.stop_requested = threading.Event()

    @property
    def url(self): return f'http://127.0.0.1:{self.port}'

    @property
    def ready(self):
        return bool(self.server and self.server.started and self.alive and not self.stop_requested.is_set())

    @property
    def alive(self): return bool(self.thread and self.thread.is_alive())

    def start(self):
        self.thread = threading.Thread(target=self._run, name='http-service', daemon=True)
        self.thread.start()

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', self.port))
            self.port = sock.getsockname()[1]
            sock.listen(128)
            import uvicorn
            from .api import create_app
            self.server = uvicorn.Server(uvicorn.Config(
                create_app(self.manager), log_config=None, access_log=False,
                proxy_headers=False, ws='wsproto', timeout_graceful_shutdown=5))
            if self.stop_requested.is_set(): return
            log.info('本地采集服务正在启动：%s', self.url)
            self.server.run(sockets=[sock])
        except OSError:
            self.error = f'服务无法启动，端口 {self.port} 可能被占用，请查看日志。'
            log.exception(self.error)
        except Exception:
            self.error = '服务启动异常，请查看日志后重新启动程序。'
            log.exception(self.error)
        finally:
            self.manager.close()
            sock.close()
            log.info('本地采集服务已停止')

    def request_stop(self):
        self.stop_requested.set()
        if self.server: self.server.should_exit = True

    def join(self, timeout=10):
        if self.thread: self.thread.join(timeout)
