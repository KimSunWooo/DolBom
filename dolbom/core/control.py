"""TCP 길이접두 JSON 제어 채널. 재연결·중복 이벤트는 상위 MessageCenter와 협력한다."""

from __future__ import annotations

import logging
import socket
import time
from typing import Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from dolbom import protocol as proto

log = logging.getLogger("dolbom.control")

GetActive = Callable[[], list[dict]]


class ControlClient(QThread):
    connection_changed = pyqtSignal(str, str)  # state, detail
    # state: idle | connecting | connected | reconnecting | error | test
    message_received = pyqtSignal(dict)
    send_failed = pyqtSignal(str)

    def __init__(self, client_id: str, get_active: GetActive):
        super().__init__()
        self.client_id = client_id
        self._get_active = get_active
        self._host = "127.0.0.1"
        self._port = 45757
        self._running = True
        self._enabled = False
        self._sock: Optional[socket.socket] = None
        self._buffer = bytearray()
        self._outbox: list[dict] = []
        self._connected = False
        self._test_mode = True
        self._backoff = 1.0

    def configure(self, host: str, port: int, enabled: bool, test_mode: bool) -> None:
        changed = (
            self._host != host
            or int(self._port) != int(port)
            or self._enabled != enabled
            or self._test_mode != test_mode
        )
        self._host = host
        self._port = int(port)
        self._enabled = enabled
        self._test_mode = test_mode
        if not enabled or changed:
            self._drop()

    def send(self, payload: dict) -> None:
        self._outbox.append(payload)

    def stop(self) -> None:
        self._running = False
        self._drop()

    def is_linked(self) -> bool:
        return self._connected

    def _drop(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._connected = False
        self._buffer = bytearray()

    def run(self) -> None:
        while self._running:
            if not self._enabled:
                self.msleep(200)
                continue
            if not self._connected:
                self._connect_once()
                if not self._connected:
                    self.msleep(int(self._backoff * 1000))
                    self._backoff = min(12.0, self._backoff * 1.6)
                    continue
            try:
                self._flush_outbox()
                self._read_available()
                self.msleep(40)
            except OSError:
                self._on_lost()
        self._drop()

    def _connect_once(self) -> None:
        label = "시험 수신기" if self._test_mode else "제어 채널"
        self.connection_changed.emit(
            "connecting" if not self._test_mode else "connecting",
            f"{label}에 연결하는 중 ({self._host}:{self._port})",
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((self._host, self._port))
            sock.settimeout(0.05)
            self._sock = sock
            self._connected = True
            self._backoff = 1.0
            hello = proto.hello(self.client_id)
            sock.sendall(proto.encode_message(hello))
            sock.sendall(proto.encode_message(proto.sync_request(self._get_active())))
            state = "test" if self._test_mode else "connected"
            detail = (
                "시험 수신기에 연결됨 — 실제 메인 서버가 아닙니다"
                if self._test_mode
                else f"제어 채널 연결됨 (초안 프로토콜 v{proto.PROTOCOL_VERSION})"
            )
            self.connection_changed.emit(state, detail)
        except OSError as exc:
            try:
                sock.close()
            except OSError:
                pass
            self._sock = None
            self._connected = False
            self.connection_changed.emit(
                "reconnecting",
                f"{label} 연결 실패, 재시도 대기 ({exc})",
            )

    def _on_lost(self) -> None:
        self._drop()
        self.connection_changed.emit("reconnecting", "연결이 끊어져 다시 연결하는 중")

    def _flush_outbox(self) -> None:
        if self._sock is None:
            return
        while self._outbox:
            payload = self._outbox.pop(0)
            try:
                self._sock.sendall(proto.encode_message(payload))
            except OSError as exc:
                self._outbox.insert(0, payload)
                raise exc

    def _read_available(self) -> None:
        if self._sock is None:
            return
        try:
            chunk = self._sock.recv(8192)
        except TimeoutError:
            return
        except socket.timeout:
            return
        except BlockingIOError:
            return
        if chunk == b"":
            raise OSError("peer closed")
        self._buffer.extend(chunk)
        while True:
            msg, self._buffer = proto.try_decode(self._buffer)
            if msg is None:
                break
            self.message_received.emit(msg)
