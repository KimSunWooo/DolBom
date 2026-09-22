from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.services import AppServices
from dolbom.models import (
    CAM_DEMO,
    CAM_DISCONNECTED,
    CAM_RECONNECTING,
    CAM_SENDING,
    CAM_STATUS_LABELS,
    MSG_URGENT,
)
from dolbom.ui.dialogs import CameraEditor, confirm
from dolbom.ui.widgets import EmptyState, StatusChip, VideoSurface, make_button


PAGE_SIZE = 2


class _CameraCard(QFrame):
    def __init__(self, services: AppServices, camera_id: str, on_open):
        super().__init__()
        self.services = services
        self.camera_id = camera_id
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        self.surface = VideoSurface("카메라 연결 준비 중")
        self.surface.clicked.connect(lambda: on_open(self.camera_id))
        self.title = QLabel()
        self.title.setObjectName("sectionTitle")
        meta = QHBoxLayout()
        self.conn = StatusChip("연결 준비 중", "muted")
        self.send = StatusChip("전송 안 함", "muted")
        meta.addWidget(self.conn)
        meta.addWidget(self.send)
        meta.addStretch()
        btns = QHBoxLayout()
        self.start_btn = make_button("전송 시작", "primary", "이 카메라 영상을 메인 서버(또는 시험 수신기)로 보냅니다.")
        self.stop_btn = make_button("전송 종료", "danger", "이 카메라의 CCTV 전송만 끝냅니다. 수집은 계속됩니다.")
        self.edit_btn = make_button("수정", tooltip="이름, 위치, 소스를 바꿉니다.")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.edit_btn.clicked.connect(self._edit)
        btns.addWidget(self.start_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.edit_btn)
        btns.addStretch()
        layout.addWidget(self.surface, 1)
        layout.addWidget(self.title)
        layout.addLayout(meta)
        layout.addLayout(btns)

    def _start(self) -> None:
        self.services.sessions.start_cctv(self.camera_id)

    def _stop(self) -> None:
        self.services.sessions.end_cctv(self.camera_id)

    def _edit(self) -> None:
        cam = self.services.store.get_camera(self.camera_id)
        if not cam:
            return
        dlg = CameraEditor(self, cam)
        if dlg.exec():
            result = dlg.result_camera()
            if result:
                self.services.store.save_camera(result)
                self.services.cameras.reload_camera(result.id)
                if not result.enabled and self.services.sessions.cctv_session(result.id):
                    self.services.sessions.end_cctv(result.id)

    def refresh_meta(self) -> None:
        cam = self.services.store.get_camera(self.camera_id)
        if not cam:
            return
        self.title.setText(f"{cam.name}  ·  {cam.location or '위치 미입력'}")
        status, detail, seen = self.services.cameras.last_status(cam.id)
        sending = self.services.sessions.is_sending_camera(cam.id)
        if sending and status not in (CAM_DISCONNECTED, CAM_RECONNECTING):
            status = CAM_SENDING
        tone = "ok"
        if status in (CAM_DISCONNECTED,):
            tone = "urgent"
        elif status in (CAM_RECONNECTING,):
            tone = "warn"
        elif status in (CAM_DEMO,):
            tone = "teal"
        elif sending:
            tone = "ok"
        label = CAM_STATUS_LABELS.get(status, status)
        if detail and status in (CAM_DISCONNECTED, CAM_RECONNECTING):
            label = f"{label}"
        self.conn.set_tone(tone, label)
        self.send.set_tone("ok" if sending else "muted", "서버 전송 중" if sending else "전송 안 함")
        live = self.services.cameras.latest(cam.id)
        last_seen = live.captured_at if live else seen
        alert = False
        latest_msg = self.services.messages.latest()
        if (
            latest_msg
            and latest_msg.severity == MSG_URGENT
            and not latest_msg.is_test
            and latest_msg.camera_id == cam.id
            and not latest_msg.acknowledged
        ):
            alert = True
        extra = ""
        if (cam.source_kind == "demo" or self.services.cameras.demo_forced()) and status != CAM_DEMO:
            extra = " · 데모"
        self.surface.set_overlay(
            title=f"{cam.name} · {cam.location}",
            status=label + extra,
            disconnected=status in (CAM_DISCONNECTED, CAM_RECONNECTING)
            and not (cam.source_kind == "demo" or self.services.cameras.demo_forced()),
            last_seen=last_seen,
            alert=alert,
        )


class CctvPage(QWidget):
    def __init__(self, services: AppServices):
        super().__init__()
        self.services = services
        self._page = 0
        self._cards: list[_CameraCard] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        head = QHBoxLayout()
        title = QLabel("병실 CCTV")
        title.setObjectName("sectionTitle")
        self.page_label = QLabel()
        self.prev_btn = make_button("이전", tooltip="이전 카메라 페이지")
        self.next_btn = make_button("다음", tooltip="다음 카메라 페이지")
        add_btn = make_button("카메라 추가", "primary", "카메라를 추가합니다. 코드 수정은 필요 없습니다.")
        empty_add = make_button("카메라 추가", "primary", "카메라를 추가합니다.")
        all_start = make_button("전체 전송 시작", tooltip="사용 중인 모든 카메라 전송을 시작합니다.")
        all_stop = make_button("전체 전송 종료", "danger", "CCTV 전송만 종료합니다. 화면을 바꿔도 수집은 유지됩니다.")
        self.prev_btn.clicked.connect(self._prev)
        self.next_btn.clicked.connect(self._next)
        add_btn.clicked.connect(self._add)
        empty_add.clicked.connect(self._add)
        all_start.clicked.connect(self._all_start)
        all_stop.clicked.connect(self._all_stop)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.page_label)
        head.addWidget(self.prev_btn)
        head.addWidget(self.next_btn)
        head.addWidget(add_btn)
        head.addWidget(all_start)
        head.addWidget(all_stop)
        self.stack = QStackedWidget()
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.empty = EmptyState(
            "등록된 카메라가 없습니다",
            "병실 영상을 보려면 카메라를 추가하세요. 기본 2대를 쓰도록 준비되어 있으며, 이후에는 화면에서 계속 늘릴 수 있습니다.",
            empty_add,
        )
        self.detail = QWidget()
        dlay = QVBoxLayout(self.detail)
        back = make_button("격자 보기로", tooltip="확대 보기를 닫고 목록으로 돌아갑니다.")
        back.clicked.connect(lambda: self.stack.setCurrentWidget(self.grid_host))
        self.detail_surface = VideoSurface("확대 보기")
        self.detail_surface.setToolTip("")
        self.detail_meta = QLabel()
        dlay.addWidget(back, alignment=Qt.AlignmentFlag.AlignLeft)
        dlay.addWidget(self.detail_surface, 1)
        dlay.addWidget(self.detail_meta)
        self._detail_id: str | None = None
        self.stack.addWidget(self.grid_host)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.detail)
        note = QLabel("메뉴를 바꿔도 CCTV 수집과 전송은 계속됩니다. 클라이언트는 낙상을 판정하지 않으며, 서버 이벤트가 오면 해당 칸을 강조합니다.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        root.addLayout(head)
        root.addWidget(self.stack, 1)
        root.addWidget(note)
        self.rebuild()
        services.cameras.frame_ready.connect(self._on_frame)
        services.cameras.status_changed.connect(lambda *_: self._refresh_meta())
        services.sessions.session_changed.connect(self._refresh_meta)
        services.messages.changed.connect(self._refresh_meta)

    def rebuild(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()
        cams = self.services.store.list_cameras()
        if not cams:
            self.stack.setCurrentWidget(self.empty)
            return
        start = self._page * PAGE_SIZE
        visible = cams[start : start + PAGE_SIZE]
        if not visible and self._page:
            self._page -= 1
            visible = cams[self._page * PAGE_SIZE : self._page * PAGE_SIZE + PAGE_SIZE]
        for i, cam in enumerate(visible):
            card = _CameraCard(self.services, cam.id, self._open)
            self._cards.append(card)
            self.grid.addWidget(card, 0, i)
        total_pages = max(1, (len(cams) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page_label.setText(f"{self._page + 1} / {total_pages} 페이지 · 카메라 {len(cams)}대")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page + 1 < total_pages)
        if self.stack.currentWidget() is self.detail:
            return
        self.stack.setCurrentWidget(self.grid_host)
        self._refresh_meta()

    def _open(self, camera_id: str) -> None:
        self._detail_id = camera_id
        self.stack.setCurrentWidget(self.detail)
        self._refresh_meta()

    def _prev(self) -> None:
        self._page = max(0, self._page - 1)
        self.rebuild()

    def _next(self) -> None:
        self._page += 1
        self.rebuild()

    def _add(self) -> None:
        dlg = CameraEditor(self, next_sort=self.services.store.next_camera_sort())
        if dlg.exec():
            cam = dlg.result_camera()
            if cam:
                self.services.store.save_camera(cam)
                self.services.cameras.reload_camera(cam.id)
                self.rebuild()

    def _all_start(self) -> None:
        for cam in self.services.store.list_cameras(include_disabled=False):
            self.services.sessions.start_cctv(cam.id)

    def _all_stop(self) -> None:
        for cam in self.services.store.list_cameras():
            self.services.sessions.end_cctv(cam.id)

    def _on_frame(self, frame) -> None:
        for card in self._cards:
            if card.camera_id == frame.camera_id:
                card.surface.set_frame(frame.bgr)
        if self._detail_id == frame.camera_id and self.stack.currentWidget() is self.detail:
            self.detail_surface.set_frame(frame.bgr)

    def _refresh_meta(self) -> None:
        for card in self._cards:
            card.refresh_meta()
        if self._detail_id:
            cam = self.services.store.get_camera(self._detail_id)
            if cam:
                self.detail_meta.setText(f"{cam.name} · {cam.location} · 클릭한 카메라는 계속 수집됩니다.")
