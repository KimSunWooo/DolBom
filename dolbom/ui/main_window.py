from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.services import AppServices
from dolbom.ui.dialogs import MessagesPanel, confirm
from dolbom.ui.pages.cctv import CctvPage
from dolbom.ui.pages.exercise import ExercisePage
from dolbom.ui.pages.gait import GaitPage
from dolbom.ui.pages.settings import SettingsPage
from dolbom.ui.widgets import MessageBar, StatusChip, make_button
from dolbom.theme import set_kind


class MainWindow(QMainWindow):
    def __init__(self, services: AppServices):
        super().__init__()
        self.services = services
        self.setWindowTitle("돌봄(DolBom)")
        self.setMinimumSize(QSize(1180, 740))
        self.resize(1360, 860)

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        top = QFrame()
        top.setObjectName("topBar")
        top.setFixedHeight(56)
        th = QHBoxLayout(top)
        th.setContentsMargins(16, 8, 16, 8)
        title = QLabel("돌봄(DolBom)")
        title.setObjectName("appTitle")
        self.conn_chip = StatusChip("제어 채널 대기", "muted")
        self.clock = QLabel()
        self.clock.setObjectName("clock")
        th.addWidget(title)
        th.addStretch()
        th.addWidget(self.conn_chip)
        th.addSpacing(16)
        th.addWidget(self.clock)

        self.demo_banner = QFrame()
        self.demo_banner.setObjectName("demoBanner")
        bh = QHBoxLayout(self.demo_banner)
        bh.setContentsMargins(16, 6, 16, 6)
        self.demo_label = QLabel()
        self.demo_label.setWordWrap(True)
        bh.addWidget(self.demo_label)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        side = QFrame()
        side.setObjectName("sideBar")
        side.setFixedWidth(188)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 16, 10, 16)
        self.nav = {}
        for key, label, tip in (
            ("cctv", "병실 CCTV", "병실 카메라 모니터링 · Ctrl+1"),
            ("exercise", "운동", "표준 영상과 환자 촬영 · Ctrl+2"),
            ("gait", "보행", "보행 실시간 촬영 · Ctrl+3"),
            ("settings", "설정", "연결·대상자·시험 메시지 · Ctrl+4"),
        ):
            b = QPushButton(label)
            set_kind(b, "nav")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.nav[key] = b
            sl.addWidget(b)
        sl.addStretch()

        self.pages = QStackedWidget()
        self.cctv_page = CctvPage(services)
        self.exercise_page = ExercisePage(services)
        self.gait_page = GaitPage(services)
        self.settings_page = SettingsPage(services)
        self.pages.addWidget(self.cctv_page)
        self.pages.addWidget(self.exercise_page)
        self.pages.addWidget(self.gait_page)
        self.pages.addWidget(self.settings_page)
        body.addWidget(side)
        body.addWidget(self.pages, 1)

        self.message_bar = MessageBar()
        self.message_bar.open_all.connect(self.open_messages)
        self._msg_panel: MessagesPanel | None = None

        v.addWidget(top)
        v.addWidget(self.demo_banner)
        v.addLayout(body, 1)
        v.addWidget(self.message_bar)

        self._page_index = {"cctv": 0, "exercise": 1, "gait": 2, "settings": 3}
        self.show_page("cctv")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)

        services.connection_changed.connect(self._on_conn)
        services.messages.changed.connect(self._refresh_messages)
        services.patients_changed.connect(self.exercise_page.reload_patients)
        services.patients_changed.connect(self.gait_page.reload_patients)
        self._refresh_messages()
        self._refresh_banner()
        self._bind_shortcuts()
        self._tick()

    def _bind_shortcuts(self) -> None:
        mapping = [("cctv", "Ctrl+1"), ("exercise", "Ctrl+2"), ("gait", "Ctrl+3"), ("settings", "Ctrl+4")]
        for key, seq in mapping:
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
            act.triggered.connect(lambda _=False, k=key: self.show_page(k))
            self.addAction(act)
        msg = QAction(self)
        msg.setShortcut(QKeySequence("Ctrl+M"))
        msg.triggered.connect(self.open_messages)
        self.addAction(msg)

    def show_page(self, key: str) -> None:
        self.pages.setCurrentIndex(self._page_index[key])
        for k, btn in self.nav.items():
            btn.setChecked(k == key)
        if key in ("exercise", "gait"):
            self.exercise_page.reload_patients()
            self.exercise_page.reload_cameras()
            self.gait_page.reload_patients()
            self.gait_page.reload_cameras()
        if key == "cctv":
            self.cctv_page.rebuild()
        if key == "settings":
            self.settings_page.reload()

    def open_messages(self) -> None:
        if self._msg_panel is None:
            self._msg_panel = MessagesPanel(self.services.store, self)
            self._msg_panel.jump_to.connect(self.show_page)
            self._msg_panel.acknowledged.connect(self._refresh_messages)
        self._msg_panel.reload()
        self._msg_panel.show()
        self._msg_panel.raise_()

    def _tick(self) -> None:
        self.clock.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.exercise_page.tick()
        self.gait_page.tick()
        self._refresh_banner()

    def _on_conn(self, state: str, detail: str) -> None:
        tones = {
            "connected": "ok",
            "test": "teal",
            "connecting": "warn",
            "reconnecting": "warn",
            "error": "urgent",
        }
        labels = {
            "connected": "제어 채널 연결됨",
            "test": "시험 수신기 연결됨",
            "connecting": "연결하는 중",
            "reconnecting": "재연결 중",
            "error": "연결 오류",
        }
        self.conn_chip.set_tone(tones.get(state, "muted"), labels.get(state, "제어 채널 대기"))
        self.conn_chip.setToolTip(detail)

    def _refresh_messages(self) -> None:
        self.message_bar.refresh(self.services.messages.unread(), self.services.messages.latest())
        if self._msg_panel and self._msg_panel.isVisible():
            self._msg_panel.reload()

    def _refresh_banner(self) -> None:
        demo = self.services.store.demo_mode()
        rx = self.services.store.get_meta("use_test_receiver", "1") == "1"
        if demo or rx:
            parts = []
            if demo:
                parts.append("데모 모드 — 합성 영상을 사용 중이며 실제 카메라가 아닙니다.")
            if rx:
                parts.append("로컬 시험 수신기 — 실제 메인 서버 연결이 아닙니다.")
            self.demo_label.setText(" ".join(parts))
            self.demo_banner.show()
        else:
            self.demo_banner.hide()

    def closeEvent(self, event) -> None:
        live = self.services.sessions.clinical()
        cctv = bool(self.services.sessions.active_payloads())
        if live or cctv:
            bits = []
            if live:
                bits.append("운동" if live.mode == "exercise" else "보행")
            if any(s.mode == "cctv" for s in [
                # duck type via payloads
            ]):
                pass
            names = []
            for payload in self.services.sessions.active_payloads():
                if payload["mode"] == "cctv":
                    names.append("CCTV 전송")
                elif payload["mode"] == "exercise":
                    names.append("운동 세션")
                elif payload["mode"] == "gait":
                    names.append("보행 세션")
            text = (
                "진행 중인 작업이 있습니다: "
                + ", ".join(dict.fromkeys(names))
                + "\n종료하면 전송과 세션이 모두 정리됩니다. 앱을 종료할까요?"
            )
            if not confirm(self, "돌봄 종료", text):
                event.ignore()
                return
        self.exercise_page.shutdown()
        self.services.shutdown()
        event.accept()
