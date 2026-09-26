import argparse
import json
import logging
import webbrowser
from .runtime import (InstanceGuard, ControlEvents, SHOW_EVENT, configure_logging,
                      signal_event, stop_running)
from . import __version__


def main():
    parser = argparse.ArgumentParser(description='Face capture service and desktop log window')
    parser.add_argument('protocol', nargs='?', default='')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--open-demo', action='store_true')
    parser.add_argument('--minimized', action='store_true', help='Start in the system tray')
    args = parser.parse_args()
    if args.protocol and args.protocol.rstrip('/') != 'facecapture://start': return 2
    if args.stop: return stop_running()
    if args.self_test:
        root = configure_logging()
        result = {'ok': False, 'modelInitialized': False}
        try:
            import numpy as np
            from .vision import FaceAnalyzer
            with FaceAnalyzer() as analyzer:
                sample = analyzer.analyze(np.zeros((480, 640, 3), dtype=np.uint8), 1000)
            result.update(ok=sample.faces == 0, modelInitialized=True)
        except Exception as exc:
            logging.exception('Self test failed')
            result['error'] = str(exc)
        (root / 'self-test.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        return 0 if result['ok'] else 1
    with InstanceGuard() as guard:
        if not guard.acquired:
            if args.open_demo: webbrowser.open('http://127.0.0.1:18765/')
            elif not args.minimized and not args.protocol:
                signal_event(SHOW_EVENT)
            return 0
        with ControlEvents() as events:
            root = configure_logging(new_session=True)
            log = logging.getLogger(__name__)
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('zookchen.FaceCapture')
                from .backend import BackendService
                from .desktop import run_desktop
                log.info('Face Capture %s starting on 127.0.0.1:18765', __version__)
                return run_desktop(BackendService(), root / 'logs', events.poll,
                                   minimized=args.minimized or bool(args.protocol),
                                   open_demo=args.open_demo)
            except Exception:
                log.exception('Desktop startup failed')
                return 1


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
