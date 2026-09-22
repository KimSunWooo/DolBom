from __future__ import annotations

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

from dolbom.core.assignment import cctv_cameras
from dolbom.core.services import AppServices
from dolbom.models import (
    CAM_DEMO,
    CAM_DISCONNECTED,
    CAM_PREPARING,
    CAM_RECONNECTING,
    CAM_SENDING,
    CAM_STATUS_LABELS,
    MSG_URGENT,
)
from dolbom.ui.device_picker import DevicePickerDialog
from dolbom.ui.dialogs import CameraLabelDialog
from dolbom.ui.patient_panel import RoomOccupants
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
        self.role = StatusChip("병실 CCTV", "teal")
        self.conn = StatusChip("연결 준비 중", "muted")
        self.send = StatusChip("전송 안 함", "muted")
        meta = QHBoxLayout()
        meta.addWidget(self.role)
        meta.addWidget(self.conn)
        meta.addWidget(self.send)
        meta.addStretch()
        self.device_lab = QLabel()
        self.device_lab.setObjectName("muted")
        self.device_lab.setWordWrap(True)
        btns = QHBoxLayout()
        self.start_btn = make_button("전송 시작", "primary", "이 카메라 영상을 서버(또는 시험 수신기)로 보냅니다.")
        self.stop_btn = make_button("전송 종료", "danger", "이 카메라의 CCTV 전송만 끝냅니다. 수집은 계속됩니다.")
        self.pick_btn = make_button("카메라 선택", tooltip="연결된 로컬 장치 목록에서 고릅니다.")
        self.retry_btn = make_button("재연결", tooltip="같은 장치로 다시 연결합니다.")
        self.label_btn = make_button("이름·위치")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.pick_btn.clicked.connect(self._pick)
        self.retry_btn.clicked.connect(self._retry)
        self.label_btn.clicked.connect(self._label)
        for b in (self.start_btn, self.stop_btn, self.pick_btn, self.retry_btn, self.label_btn):
            btns.addWidget(b)
        btns.addStretch()
        self.occupants = RoomOccupants(services.patients)
        layout.addWidget(self.surface, 1)
        layout.addWidget(self.title)
        layout.addLayout(meta)
        layout.addWidget(self.device_lab)
        layout.addLayout(btns)
        layout.addWidget(self.occupants)

    def _start(self) -> None:
        self.services.sessions.start_cctv(self.camera_id)

    def _stop(self) -> None:
        self.services.sessions.end_cctv(self.camera_id)

    def _pick(self) -> None:
        cam = self.services.store.get_camera(self.camera_id)
        if not cam:
            return
        dlg = DevicePickerDialog(self.services, cam, self)
        dlg.exec()

    def _retry(self) -> None:
        self.services.cameras.reopen(self.camera_id)

    def _label(self) -> None:
        cam = self.services.store.get_camera(self.camera_id)
        if not cam:
            return
        dlg = CameraLabelDialog(self, cam)
        if dlg.exec():
            self.services.store.save_camera(dlg.apply_to(cam))
            self.services.cameras_changed.emit()

    def refresh_meta(self) -> None:
        cam = self.services.store.get_camera(self.camera_id)
        if not cam:
            return
        self.title.setText(f"{cam.name}  ·  {cam.location or '위치 미입력'}")
        self.role.set_tone("teal", cam.role_text())
        status, detail, seen = self.services.cameras.last_status(cam.id)
        sending = self.services.sessions.is_sending_camera(cam.id)
        if sending and status not in (CAM_DISCONNECTED, CAM_RECONNECTING, CAM_PREPARING):
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
        self.conn.set_tone(tone, label)
        self.send.set_tone("ok" if sending else "muted", "서버 전송 중" if sending else "전송 안 함")
        src = cam.display_source()
        if not cam.device_id and cam.source_kind != "rtsp":
            src = "장치가 아직 연결되지 않았습니다. [카메라 선택]으로 지정하세요."
        if detail and status in (CAM_DISCONNECTED, CAM_RECONNECTING, CAM_PREPARING):
            src = detail
        self.device_lab.setText(src)
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
        if cam.is_demo_source() and status != CAM_DEMO:
            extra = " · 데모 모드" if self.services.cameras.demo_forced() else ""
        disconnected = status in (CAM_DISCONNECTED, CAM_RECONNECTING)
        no_live = live is None or disconnected
        overlay = label + extra
        if detail and status in (CAM_DISCONNECTED, CAM_RECONNECTING, CAM_PREPARING):
            overlay = detail
        elif disconnected:
            overlay = f"{label} · 재연결 또는 장치를 다시 선택하세요"
        if no_live:
            self.surface.clear_frame()
            self.surface.set_placeholder(overlay or "영상 없음")
        self.surface.set_overlay(
            title=f"{cam.name} · {cam.location}",
            status=overlay,
            disconnected=disconnected,
            last_seen=last_seen,
            alert=alert,
        )
        if getattr(self, "_occ_loc", None) != cam.location:
            self._occ_loc = cam.location
            self.occupants.load_location(cam.location)


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
        add_btn = make_button("카메라 추가", "primary", "병실 CCTV 슬롯을 추가합니다.")
        empty_add = make_button("카메라 추가", "primary")
        all_start = make_button("전체 전송 시작")
        all_stop = make_button("전체 전송 종료", "danger")
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
            "등록된 병실 CCTV가 없습니다",
            "병실 CCTV 슬롯을 추가한 뒤 [카메라 선택]으로 장치를 지정하세요. 운동·보행 카메라는 이 화면에 나오지 않습니다.",
            empty_add,
        )
        self.detail = QWidget()
        dlay = QVBoxLayout(self.detail)
        back = make_button("격자 보기로")
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
        note = QLabel(
            "메뉴를 바꿔도 CCTV 수집과 전송은 계속됩니다. "
            "서버 이벤트에 환자 신원이 없으면 임의의 환자를 연결하지 않습니다."
        )
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
        services.cameras_changed.connect(self.rebuild)

    def _cctv_list(self):
        return cctv_cameras(self.services.store.list_cameras())

    def rebuild(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()
        cams = self._cctv_list()
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
        self.page_label.setText(f"{self._page + 1} / {total_pages} 페이지 · 병실 CCTV {len(cams)}대")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page + 1 < total_pages)
        if self.stack.currentWidget() is not self.detail:
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
        cam = self.services.add_cctv_slot()
        dlg = DevicePickerDialog(self.services, cam, self)
        dlg.exec()
        self.rebuild()

    def _all_start(self) -> None:
        for cam in self._cctv_list():
            if cam.enabled:
                self.services.sessions.start_cctv(cam.id)

    def _all_stop(self) -> None:
        for cam in self._cctv_list():
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
                status, detail, seen = self.services.cameras.last_status(cam.id)
                live = self.services.cameras.latest(cam.id)
                self.detail_meta.setText(
                    f"{cam.role_text()} · {cam.name} · {cam.location} · 수집은 계속됩니다."
                )
                if live is None or status in (CAM_DISCONNECTED, CAM_RECONNECTING):
                    self.detail_surface.clear_frame()
                overlay = detail or CAM_STATUS_LABELS.get(status, status)
                self.detail_surface.set_overlay(
                    f"{cam.name} · {cam.location}",
                    overlay,
                    disconnected=status in (CAM_DISCONNECTED, CAM_RECONNECTING),
                    last_seen=live.captured_at if live else seen,
                )
