"""Real desktop UI on an isolated test port; does not replace installed service."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    import logging
    from face_capture.backend import BackendService
    from face_capture.desktop import run_desktop
    from face_capture.runtime import configure_logging, ControlEvents
    root = configure_logging()
    logging.info('桌面界面验收：独立测试服务，不使用已安装服务或摄像头。')
    with ControlEvents('FaceCaptureFixtureStop', 'FaceCaptureFixtureShow') as events:
        raise SystemExit(run_desktop(BackendService(port=18768), root / 'logs', events.poll))
