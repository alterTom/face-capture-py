import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtCore import Qt
from face_capture.desktop import DesktopWindow


class FakeBackend:
    url = 'http://127.0.0.1:18765'
    ready = True
    alive = True
    error = None
    stop_calls = 0
    def request_stop(self): self.stop_calls += 1


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'test-output')
        self.addCleanup(self.temp.cleanup)
        self.logs = Path(self.temp.name)
        self.backend = FakeBackend()
        self.window = DesktopWindow(self.backend, self.logs)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.timer.stop()
        self.window.tray.hide()
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()

    def test_close_hides_window_but_does_not_stop_service(self):
        with patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=True):
            self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertEqual(self.backend.stop_calls, 0)
        self.assertFalse(self.app.quitOnLastWindowClosed())
        self.window.tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertTrue(self.window.isVisible())
        self.assertNotEqual(self.window.windowFlags() & Qt.WindowType.WindowType_Mask, Qt.WindowType.Tool)

    def test_no_system_tray_falls_back_to_taskbar_minimize(self):
        with patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False):
            self.window.close()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.isMinimized())
        self.assertEqual(self.backend.stop_calls, 0)

    def test_button_opens_test_page_only_when_ready(self):
        self.window.refresh()
        with patch('face_capture.desktop.webbrowser.open', return_value=True) as opener:
            self.window.open_button.click()
            opener.assert_called_once_with('http://127.0.0.1:18765/')
        self.backend.ready = False
        self.window.refresh()
        self.assertFalse(self.window.open_button.isEnabled())

    def test_log_display_updates_and_is_read_only(self):
        (self.logs / 'capture.log').write_text('采集任务开始\n', encoding='utf-8')
        (self.logs / 'camera.log').write_text('摄像头打开\n', encoding='utf-8')
        self.window.refresh()
        text = self.window.log_view.toPlainText()
        self.assertIn('采集任务开始', text)
        self.assertIn('摄像头打开', text)
        self.assertTrue(self.window.log_view.isReadOnly())
        self.window.refresh()
        self.assertEqual(text, self.window.log_view.toPlainText())

    def test_tray_exit_requests_shutdown_once_and_waits_for_backend(self):
        with patch.object(self.app, 'quit') as quit_app:
            self.window.exit_action.trigger()
            self.window.request_exit()
            self.assertEqual(self.backend.stop_calls, 1)
            self.window.refresh()
            quit_app.assert_not_called()
            self.backend.alive = False
            self.window.refresh()
            quit_app.assert_called_once()
