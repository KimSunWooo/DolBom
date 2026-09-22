"""앱 서비스 조립. UI는 이 객체의 시그널만 사용한다."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from dolbom import protocol as proto
from dolbom.core.camera_hub import CameraHub
from dolbom.core.control import ControlClient
from dolbom.core.messages import MessageCenter
from dolbom.core.samples import ensure_samples
from dolbom.core.sender import StreamSender
from dolbom.core.session import SessionManager
from dolbom.db.store import Store
from dolbom.models import CAM_DISCONNECTED, MSG_SERVER_ERROR
from dolbom.paths import db_path
from dolbom.tools.test_receiver import TestReceiver

log = logging.getLogger("dolbom.services")


class AppServices(QObject):
    connection_changed = pyqtSignal(str, str)
    patients_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.store = Store(db_path())
        self.cameras = CameraHub(self.store)
        self.sender = StreamSender(self.cameras.latest)
        self.messages = MessageCenter(self.store)
        self.messages.set_sound(self.store.get_meta("alert_sound", "1") == "1")
        self.control = ControlClient(self.store.client_id(), self._active)
        self.sessions = SessionManager(self.store, self.sender, self.control)
        self.receiver: TestReceiver | None = None
        self._conn_state = ""
        self._cam_status: dict[str, str] = {}
        self.control.connection_changed.connect(self._on_conn)
        self.control.message_received.connect(self._on_control_msg)
        self.cameras.status_changed.connect(self._on_cam_status)

    def _active(self) -> list[dict]:
        return self.sessions.active_payloads()

    def start(self) -> None:
        try:
            items = ensure_samples()
            self.store.ensure_sample_playlist(items)
        except Exception:
            log.exception("sample video generation failed")
        self.apply_network_settings()
        self.sender.start()
        self.control.start()
        self.cameras.start_enabled()

    def apply_network_settings(self) -> None:
        host = self.store.get_meta("server_host", "127.0.0.1")
        tcp = int(self.store.get_meta("tcp_port", "45757") or 45757)
        udp = int(self.store.get_meta("udp_port", "45004") or 45004)
        demo = self.store.demo_mode()
        use_rx = self.store.get_meta("use_test_receiver", "1") == "1"
        self.cameras.set_demo_forced(demo)
        self.sender.configure(host, udp)
        self.messages.set_sound(self.store.get_meta("alert_sound", "1") == "1")
        self._stop_receiver()
        if use_rx:
            self._ensure_receiver(host, tcp, udp)
        self.control.configure(host, tcp, enabled=True, test_mode=use_rx)

    def _ensure_receiver(self, host: str, tcp: int, udp: int) -> None:
        try:
            self.receiver = TestReceiver(host, tcp, udp)
            self.receiver.start()
        except OSError:
            log.warning("test receiver bind failed; will try connecting anyway")
            self.receiver = None

    def _stop_receiver(self) -> None:
        if self.receiver:
            self.receiver.stop()
            self.receiver = None

    def _on_conn(self, state: str, detail: str) -> None:
        prev = self._conn_state
        self._conn_state = state
        self.connection_changed.emit(state, detail)
        if state == "reconnecting" and prev in ("connected", "test"):
            self.messages.add(
                severity=MSG_SERVER_ERROR,
                content=detail,
                navigate_to="settings",
            )

    def _on_control_msg(self, payload: dict) -> None:
        msg_type = payload.get("type")
        if msg_type == proto.MSG_EVENT:
            self.messages.from_server(payload)
        elif msg_type == proto.MSG_HELLO_ACK:
            note = payload.get("note") or "제어 채널 응답을 받았습니다."
            # 생산 서버 연동 완료로 표시하지 않는다.
            self.connection_changed.emit(
                "test" if self.store.get_meta("use_test_receiver", "1") == "1" else "connected",
                note,
            )
        elif msg_type == proto.MSG_SYNC:
            self.control.send(proto.sync_request(self._active()))

    def _on_cam_status(self, camera_id: str, status: str, detail: str) -> None:
        prev = self._cam_status.get(camera_id)
        self._cam_status[camera_id] = status
        if status == CAM_DISCONNECTED and prev != CAM_DISCONNECTED:
            cam = self.store.get_camera(camera_id)
            loc = cam.location if cam else ""
            name = cam.name if cam else camera_id
            self.messages.add(
                severity="camera_error",
                content=detail or f"{name} 연결이 끊겼습니다.",
                camera_id=camera_id,
                location=loc,
                navigate_to="cctv",
            )

    def shutdown(self) -> None:
        self.sessions.end_all()
        self.cameras.stop_all()
        self.sender.stop()
        self.control.stop()
        self.sender.wait(2000)
        self.control.wait(2000)
        self._stop_receiver()
        self.store.close()
