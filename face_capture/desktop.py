"""Desktop log window and tray; camera preview remains in the browser."""
import logging
import os
import webbrowser
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QPlainTextEdit, QPushButton, QStyle, QSystemTrayIcon,
                               QVBoxLayout, QWidget)
from . import __version__
from .log_reader import LogTail
from .paths import resource_path

log = logging.getLogger(__name__)


class DesktopWindow(QMainWindow):
    def __init__(self, backend, log_directory, poll_events=None, open_when_ready=False):
        super().__init__()
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.backend = backend
        self.log_directory = Path(log_directory)
        self.poll_events = poll_events
        self.open_when_ready = open_when_ready
        self.stopping = False
        self.error_shown = False
        self.finished = False
        self.setWindowTitle(f'人脸采集服务 · 日志 v{__version__}')
        self.resize(960, 640)
        self.setMinimumSize(640, 440)
        icon = QIcon(str(resource_path('assets/face-capture.ico')))
        if icon.isNull(): icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        header = QHBoxLayout()
        title = QLabel('人脸采集服务')
        title.setObjectName('heading')
        header.addWidget(title)
        header.addStretch()
        self.open_button = QPushButton('打开测试页')
        self.open_button.setObjectName('primary')
        self.open_button.clicked.connect(self.open_test_page)
        header.addWidget(self.open_button)
        layout.addLayout(header)
        self.status_label = QLabel('正在启动本地采集服务…')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        caption = QLabel('采集过程日志')
        caption.setObjectName('caption')
        layout.addWidget(caption)
        self.log_view = QPlainTextEdit()
        self.log_view.setAccessibleName('采集过程日志')
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setFont(QFont('Consolas', 10))
        self.log_view.setPlaceholderText('等待采集任务。浏览器开始采集后，过程日志会自动显示在这里。')
        layout.addWidget(self.log_view, 1)
        footer = QHBoxLayout()
        note = QLabel('关闭窗口后继续在托盘运行；右键托盘图标可退出程序。')
        note.setWordWrap(True)
        footer.addWidget(note, 1)
        self.logs_button = QPushButton('打开日志文件夹')
        self.logs_button.clicked.connect(self.open_logs)
        footer.addWidget(self.logs_button)
        layout.addLayout(footer)
        self.setCentralWidget(root)
        self.setStyleSheet('''
            QMainWindow, QWidget { background: #f5f7fb; color: #24354b; }
            QLabel#heading { font-size: 23px; font-weight: 600; }
            QLabel#caption { font-weight: 600; }
            QPlainTextEdit { background: #ffffff; border: 1px solid #d6deea;
                             border-radius: 8px; padding: 10px; }
            QPushButton { background: #e5ebf3; border: 0; border-radius: 6px;
                          padding: 10px 16px; }
            QPushButton:hover { background: #d8e3f2; }
            QPushButton#primary { background: #2463df; color: white; }
            QPushButton#primary:hover { background: #1b52c2; }
            QPushButton:disabled { background: #dfe5ed; color: #8895a5; }
        ''')

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(f'人脸采集服务 v{__version__}')
        self.tray_menu = QMenu()
        self.show_action = QAction('显示日志窗口', self)
        self.show_action.triggered.connect(self.show_window)
        self.tray_menu.addAction(self.show_action)
        self.test_action = QAction('打开测试页', self)
        self.test_action.triggered.connect(self.open_test_page)
        self.tray_menu.addAction(self.test_action)
        self.tray_menu.addSeparator()
        self.exit_action = QAction('退出程序', self)
        self.exit_action.triggered.connect(self.request_exit)
        self.tray_menu.addAction(self.exit_action)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.tails = [('服务', LogTail(self.log_directory / 'capture.log')),
                      ('采集', LogTail(self.log_directory / 'camera.log'))]
        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def show_window(self):
        if self.finished: return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def closeEvent(self, event):
        if self.finished:
            event.accept()
            return
        event.ignore()
        if QSystemTrayIcon.isSystemTrayAvailable(): self.hide()
        else: self.showMinimized()

    def open_test_page(self):
        if self.backend.ready and not self.stopping:
            webbrowser.open(self.backend.url + '/')

    def open_logs(self):
        self.log_directory.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.log_directory))

    def request_exit(self):
        if self.stopping: return
        self.stopping = True
        self.open_when_ready = False
        self.exit_action.setEnabled(False)
        self.open_button.setEnabled(False)
        self.test_action.setEnabled(False)
        self.backend.request_stop()
        self.status_label.setText('正在停止服务并释放摄像头，请稍候…')
        log.info('用户请求退出，正在停止采集服务')

    def refresh(self):
        if self.finished: return
        if self.poll_events:
            stop, show = self.poll_events()
            if stop: self.request_exit()
            elif show: self.show_window()
        lines = []
        for source, tail in self.tails:
            lines.extend(f'[{source}] {line}' for line in tail.read_lines())
        if lines:
            scrollbar = self.log_view.verticalScrollBar()
            old_position = scrollbar.value()
            follow = old_position >= scrollbar.maximum() - 4
            self.log_view.appendPlainText('\n'.join(lines))
            scrollbar.setValue(scrollbar.maximum() if follow else old_position)
        if self.stopping:
            if not self.backend.alive:
                self.finished = True
                self.timer.stop()
                self.tray.hide()
                self.close()
                QApplication.instance().quit()
            return
        ready = self.backend.ready
        self.open_button.setEnabled(ready)
        self.test_action.setEnabled(ready)
        if self.backend.error:
            self.status_label.setText(self.backend.error)
            self.status_label.setStyleSheet('color: #b32636;')
            self.tray.setToolTip('人脸采集服务 — 启动失败，请查看日志')
            if not self.error_shown:
                self.error_shown = True
                self.show_window()
        elif ready:
            self.status_label.setText(f'● 服务运行中    {self.backend.url}')
            self.status_label.setStyleSheet('color: #247258;')
            self.tray.setToolTip(f'人脸采集服务 v{__version__} — 运行中')
            if self.open_when_ready:
                self.open_when_ready = False
                self.open_test_page()
        else:
            self.status_label.setText('正在启动本地采集服务…')


def run_desktop(backend, log_directory, poll_events, minimized=False, open_demo=False):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName('FaceCapture')
    app.setApplicationVersion(__version__)
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyle('Fusion')
    app.aboutToQuit.connect(backend.request_stop)
    backend.start()
    window = DesktopWindow(backend, log_directory, poll_events, open_demo)
    if not minimized: window.show()
    elif not QSystemTrayIcon.isSystemTrayAvailable(): window.showMinimized()
    try:
        return app.exec()
    finally:
        window.timer.stop()
        window.tray.hide()
        backend.request_stop()
        backend.join(15)
