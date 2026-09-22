"""OS 연결 카메라 선택. 탐색·미리보기는 작업 스레드에서 수행한다."""

from __future__ import annotations

import uuid

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.capture import CaptureWorker
from dolbom.core.devices import PhysicalDevice, list_demo_devices, list_local_devices, _id_match
from dolbom.core.qtutil import keep_thread, join_worker
from dolbom.core.services import AppServices
from dolbom.models import SOURCE_DEMO, Camera
from dolbom.ui.widgets import StatusChip, VideoSurface, make_button


class _EnumThread(QThread):
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, include_demo: bool, token: int):
        super().__init__()
        self.include_demo = include_demo
        self.token = token

    def run(self) -> None:
        try:
            devices = list_local_devices()
            if self.include_demo:
                devices = devices + list_demo_devices()
            self.done.emit(devices)
        except Exception as exc:
            self.failed.emit(str(exc))


class NetworkCameraDialog(QDialog):
    def __init__(self, parent=None, current: str = ""):
        super().__init__(parent)
        self.setWindowTitle("네트워크 카메라 추가")
        layout = QVBoxLayout(self)
        hint = QLabel(
            "IP CCTV는 로컬 장치 목록에 자동으로 나타나지 않습니다. "
            "RTSP 주소를 직접 입력하세요. 네트워크 자동 탐색은 제공하지 않습니다."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form = QFormLayout()
        self.url = QLineEdit(current)
        self.url.setPlaceholderText("rtsp://사용자:비밀번호@호스트/경로")
        form.addRow("주소", self.url)
        note = QLabel("접속 비밀번호는 로그에 남기지 않습니다.")
        note.setObjectName("muted")
        row = QHBoxLayout()
        ok = make_button("연결", "primary")
        cancel = make_button("취소")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addLayout(row)
        self.resize(520, 220)

    def address(self) -> str:
        return self.url.text().strip()


class DevicePickerDialog(QDialog):
    def __init__(self, services: AppServices, camera: Camera, parent=None):
        super().__init__(parent)
        self.services = services
        self.camera = camera
        self._devices: list[PhysicalDevice] = []
        self._enum: _EnumThread | None = None
        self._enum_token = 0
        self._preview_worker: CaptureWorker | None = None
        self._preview_id = ""
        self._reuse_id = ""
        self.setWindowTitle(f"카메라 선택 — {camera.role_text()}")
        layout = QVBoxLayout(self)
        intro = QLabel(
            f"용도: {camera.role_text()}. USB·내장 카메라는 아래 목록에서 고르고, "
            "같은 이름의 장치는 식별 정보로 구분하세요. 이미 수집 중인 장치는 다시 열지 않습니다."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        self.status = StatusChip("장치 목록을 읽는 중", "warn")
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        self.preview = VideoSurface("미리보기를 누르면 영상이 표시됩니다")
        self.preview.setToolTip("선택 전 구도 확인")
        try:
            self.preview.clicked.disconnect()
        except TypeError:
            pass
        self.detail = QLabel("목록에서 장치를 선택하세요.")
        self.detail.setWordWrap(True)
        btns = QHBoxLayout()
        self.refresh_btn = make_button("장치 새로고침", tooltip="OS 연결 목록을 다시 읽습니다. 화면은 멈추지 않습니다.")
        self.preview_btn = make_button("미리보기")
        self.pick_btn = make_button("선택", "primary")
        net_btn = make_button("네트워크 카메라 추가", tooltip="IP CCTV 주소를 직접 입력합니다.")
        cancel = make_button("닫기")
        self.refresh_btn.clicked.connect(self.refresh)
        self.preview_btn.clicked.connect(self._start_preview)
        self.pick_btn.clicked.connect(self._choose)
        net_btn.clicked.connect(self._network)
        cancel.clicked.connect(self.reject)
        btns.addWidget(self.refresh_btn)
        btns.addWidget(self.preview_btn)
        btns.addWidget(net_btn)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(self.pick_btn)
        layout.addWidget(intro)
        layout.addWidget(self.status)
        split = QHBoxLayout()
        split.addWidget(self.list, 3)
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(self.detail)
        split.addLayout(right, 2)
        layout.addLayout(split, 1)
        layout.addLayout(btns)
        self.resize(860, 520)
        services.cameras.frame_ready.connect(self._on_hub_frame)
        self.refresh()

    def refresh(self) -> None:
        self._stop_temp_preview()
        self.status.set_tone("warn", "장치 목록을 읽는 중")
        self.refresh_btn.setEnabled(False)
        demo = self.services.store.demo_mode()
        self._enum_token += 1
        token = self._enum_token
        thread = _EnumThread(include_demo=demo, token=token)
        thread.done.connect(lambda devices, t=thread: self._fill(t.token, devices))
        thread.failed.connect(lambda err, t=thread: self._enum_fail(t.token, err))
        thread.finished.connect(lambda: self.refresh_btn.setEnabled(True))
        self._enum = keep_thread(self, thread)
        thread.start()

    def _enum_fail(self, token: int, err: str) -> None:
        if token != self._enum_token:
            return
        self.status.set_tone("urgent", "장치 목록을 읽지 못했습니다")
        self.detail.setText(err)

    def _fill(self, token: int, devices: list) -> None:
        if token != self._enum_token:
            return
        self._devices = devices
        self.list.clear()
        assigned = [c for c in self.services.store.list_cameras() if c.device_id]
        local = [d for d in devices if d.kind != "demo"]
        demo = [d for d in devices if d.kind == "demo"]
        if not local:
            empty = QListWidgetItem("연결된 로컬 카메라가 없습니다. IP CCTV는 ‘네트워크 카메라 추가’를 사용하세요.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        for dev in local:
            self._add_item(dev, assigned)
        if demo:
            sep = QListWidgetItem("—— 개발용 데모 장치 (실제 카메라 아님) ——")
            sep.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(sep)
            for dev in demo:
                self._add_item(dev, assigned)
        n_local = len(local)
        extra = f" · 데모 {len(demo)}대" if demo else ""
        self.status.set_tone("teal", f"로컬 장치 {n_local}대{extra}")

    def _add_item(self, dev: PhysicalDevice, assigned: list) -> None:
        cam = next((c for c in assigned if _id_match(c.device_id, dev.stable_id)), None)
        use = f"현재 할당: {cam.role_text()}" if cam else "할당 없음"
        conn = "연결됨" if dev.connected else "장치 파일 없음"
        if not dev.unique:
            conn = "식별 불완전 · 재선택 권장"
        kind = "데모" if dev.kind == "demo" else "로컬"
        running = self.services.cameras.camera_id_for_device(dev.stable_id)
        if running:
            conn = "수집 중 (기존 서비스 재사용)"
        text = f"{dev.display_name}\n{dev.distinguish_label()}\n{kind} · {conn} · {use}"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, dev.stable_id)
        self.list.addItem(item)

    def _current_device(self) -> PhysicalDevice | None:
        item = self.list.currentItem()
        if not item:
            return None
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid:
            return None
        return next((d for d in self._devices if d.stable_id == sid), None)

    def _on_select(self) -> None:
        self._stop_temp_preview()
        dev = self._current_device()
        if not dev:
            return
        note = dev.extra_note or ""
        self.detail.setText(
            f"{dev.distinguish_label()}\n열기 경로: {dev.open_path}\n{note}".strip()
        )
        reuse = self.services.cameras.camera_id_for_device(dev.stable_id)
        self._reuse_id = reuse or ""
        if reuse:
            frame = self.services.cameras.latest(reuse)
            if frame is not None:
                self.preview.set_frame(frame.bgr)
            self.preview.set_overlay("미리보기", "사용 중인 수집 서비스를 재사용합니다", False)
        else:
            self.preview.clear_frame()
            self.preview.set_placeholder("미리보기를 누르면 이 장치만 잠시 엽니다")

    def _start_preview(self) -> None:
        dev = self._current_device()
        if not dev:
            return
        reuse = self.services.cameras.camera_id_for_device(dev.stable_id)
        if reuse:
            self._reuse_id = reuse
            self.preview.set_overlay("미리보기", "기존 수집 재사용 · 장치를 다시 열지 않음", False)
            return
        self._stop_temp_preview()
        self._preview_id = f"preview-{uuid.uuid4().hex[:8]}"
        temp = Camera(
            id=self._preview_id,
            name=dev.display_name,
            location="미리보기",
            source_kind=SOURCE_DEMO if dev.kind == "demo" else "device",
            source_value=dev.open_path if dev.kind != "demo" else dev.stable_id.split(":")[-1],
            device_id=dev.stable_id,
            device_path=dev.open_path,
            device_name=dev.display_name,
        )
        worker = CaptureWorker(temp, demo_forced=False)
        worker.frame_ready.connect(self._on_temp_frame)
        self._preview_worker = worker
        worker.start()
        self.preview.set_overlay("미리보기", "임시 미리보기 · 선택 전 장치만 엽니다", False)

    def _on_temp_frame(self, frame) -> None:
        if frame.camera_id == self._preview_id:
            self.preview.set_frame(frame.bgr)

    def _on_hub_frame(self, frame) -> None:
        if self._reuse_id and frame.camera_id == self._reuse_id:
            self.preview.set_frame(frame.bgr)

    def _stop_temp_preview(self) -> None:
        self._reuse_id = ""
        worker = self._preview_worker
        self._preview_worker = None
        if worker:
            worker.stop()
            join_worker(worker, 2500)

    def _choose(self) -> None:
        dev = self._current_device()
        if not dev:
            return
        if not dev.unique and dev.kind != "demo":
            self.detail.setText(
                "이 장치는 확실하게 구분할 수 없습니다. 재연결 후 잘못된 카메라가 열릴 수 있어 선택하지 않습니다. "
                "케이블을 바꾸거나 네트워크 카메라 경로를 사용하세요."
            )
            return
        self._stop_temp_preview()
        ok, reason = self.services.assign_device(self.camera.id, dev)
        if not ok:
            self.detail.setText(reason)
            return
        self.accept()

    def _network(self) -> None:
        current = self.camera.source_value if self.camera.source_kind == "rtsp" else ""
        dlg = NetworkCameraDialog(self, current)
        if dlg.exec():
            ok, reason = self.services.assign_network(self.camera.id, dlg.address())
            if ok:
                self.accept()
            else:
                self.detail.setText(reason)

    def closeEvent(self, event) -> None:
        self._stop_temp_preview()
        try:
            self.services.cameras.frame_ready.disconnect(self._on_hub_frame)
        except TypeError:
            pass
        if self._enum and self._enum.isRunning():
            self._enum.wait(800)
        super().closeEvent(event)
