"""Bounded camera lifetime even when a native driver call blocks indefinitely."""
import logging
import multiprocessing
import queue
from types import SimpleNamespace
from .sessions import ServiceError

log = logging.getLogger(__name__)


class ProcessOutput:
    def __init__(self, messages): self.messages = messages

    def _send(self, item):
        try:
            self.messages.put_nowait(item)
        except queue.Full:
            try: self.messages.get_nowait()
            except queue.Empty: pass
            try: self.messages.put(item, timeout=.1)
            except queue.Full: return False
        return True

    def publish(self, sid, preview=None, progress=None):
        self._send(('progress', progress, preview))
        return True

    def finish(self, sid, photo): self.messages.put(('success', photo), timeout=3)
    def fail(self, sid, code, message): self.messages.put(('error', code, message), timeout=3)


def camera_process(sid, actions, index, cancel, messages):
    from .runtime import configure_logging
    configure_logging('camera')
    output = ProcessOutput(messages)
    try:
        from .vision import capture
        session = SimpleNamespace(id=sid, actions=actions, camera_index=index, cancel=cancel)
        capture(session, output)
    except ServiceError as exc:
        output.fail(sid, exc.code, exc.message)
    except Exception:
        log.exception('Camera subprocess failed for %s', sid)
        output.fail(sid, 'CAPTURE_ERROR', '采集异常，请查看本地日志后重试')


def run_isolated(session, manager, target=camera_process):
    context = multiprocessing.get_context('spawn')
    cancel = context.Event()
    messages = context.Queue(maxsize=3)
    process = context.Process(target=target,
                              args=(session.id, session.actions, session.camera_index, cancel, messages),
                              daemon=True, name='FaceCaptureCamera')
    started = False
    try:
        if session.cancel.is_set(): return
        process.start()
        started = True
        log.info('Camera subprocess started pid=%s session=%s', process.pid, session.id)
        while not session.cancel.is_set():
            try: item = messages.get(timeout=.1)
            except queue.Empty:
                if not process.is_alive():
                    manager.fail(session.id, 'CAMERA_PROCESS_EXIT', '采集进程意外退出，请查看日志')
                    break
                continue
            if item[0] == 'progress':
                if not manager.publish(session.id, progress=item[1], preview=item[2]): break
            elif item[0] == 'success':
                manager.finish(session.id, photo=item[1])
                break
            elif item[0] == 'error':
                manager.fail(session.id, item[1], item[2])
                break
    finally:
        cancel.set()
        if started:
            forced = False
            log.info('请求停止摄像头采集进程：编号=%s，任务=%s，pid=%s，状态=%s，原因=%s',
                     session.camera_index, session.id, process.pid, session.status, session.error_code or '正常结束')
            process.join(timeout=.7)
            if process.is_alive():
                forced = True
                log.warning('摄像头采集进程未及时退出，正在强制终止：编号=%s，任务=%s，pid=%s',
                            session.camera_index, session.id, process.pid)
                process.terminate()
                process.join(timeout=3)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            if process.is_alive():
                # Do not release the busy flag while the device owner is still alive.
                log.error('Waiting for unresponsive camera process pid=%s', process.pid)
                process.join()
            log.info('摄像头采集进程已退出：编号=%s，任务=%s，pid=%s，退出码=%s，强制终止=%s',
                     session.camera_index, session.id, process.pid, process.exitcode, forced)
            process.close()
        messages.close()
