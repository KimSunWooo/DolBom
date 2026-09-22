"""최신 프레임만 JPEG로 나눠 UDP/RTP 전송. UI 스레드에서 인코딩하지 않는다."""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
from PyQt6.QtCore import QThread, pyqtSignal

from dolbom.models import VideoFrame
from dolbom.rtp_jpeg import packetize_jpeg, rtp_timestamp

log = logging.getLogger("dolbom.sender")

GetFrame = Callable[[str], Optional[VideoFrame]]


@dataclass
class StreamSpec:
    camera_id: str
    stream_id: str
    session_id: str
    mode: str
    ssrc: int
    max_width: int = 480
    jpeg_quality: int = 55
    seq: int = 0
    last_sent_no: int = -1
    packets_sent: int = 0
    last_error: str = ""
    last_send_ok: float = 0.0


def ssrc_from(stream_id: str) -> int:
    return abs(hash(stream_id)) & 0xFFFFFFFF


class StreamSender(QThread):
    stream_stats = pyqtSignal(str, dict)  # stream_id, stats

    def __init__(self, get_frame: GetFrame):
        super().__init__()
        self._get_frame = get_frame
        self._running = True
        self._host = "127.0.0.1"
        self._port = 45004
        self._sock: Optional[socket.socket] = None
        self._streams: dict[str, StreamSpec] = {}
        self._enabled = True

    def configure(self, host: str, port: int) -> None:
        self._host = host
        self._port = int(port)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def upsert(self, spec: StreamSpec) -> None:
        current = self._streams.get(spec.stream_id)
        if current:
            spec.seq = current.seq
            spec.packets_sent = current.packets_sent
        self._streams[spec.stream_id] = spec

    def remove(self, stream_id: str) -> None:
        self._streams.pop(stream_id, None)

    def remove_session(self, session_id: str) -> None:
        drop = [sid for sid, sp in self._streams.items() if sp.session_id == session_id]
        for sid in drop:
            self._streams.pop(sid, None)

    def active_ids(self) -> list[str]:
        return list(self._streams.keys())

    def has_camera(self, camera_id: str) -> bool:
        return any(s.camera_id == camera_id for s in self._streams.values())

    def stop(self) -> None:
        self._running = False

    def _ensure_sock(self) -> socket.socket:
        if self._sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            self._sock = sock
        return self._sock

    def run(self) -> None:
        while self._running:
            if not self._enabled or not self._streams:
                self.msleep(40)
                continue
            sock = self._ensure_sock()
            dest = (self._host, self._port)
            for spec in list(self._streams.values()):
                frame = self._get_frame(spec.camera_id)
                if frame is None or frame.frame_no == spec.last_sent_no:
                    continue
                try:
                    packets = self._encode(spec, frame)
                    for pkt in packets:
                        sock.sendto(pkt, dest)
                    spec.last_sent_no = frame.frame_no
                    spec.packets_sent += len(packets)
                    spec.last_send_ok = time.time()
                    spec.last_error = ""
                    if spec.packets_sent % 30 == 0:
                        self.stream_stats.emit(
                            spec.stream_id,
                            {
                                "packets": spec.packets_sent,
                                "ok": True,
                                "host": self._host,
                                "port": self._port,
                            },
                        )
                except OSError as exc:
                    spec.last_error = str(exc)
                    self.stream_stats.emit(
                        spec.stream_id,
                        {"ok": False, "error": spec.last_error},
                    )
            self.msleep(20)
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _encode(self, spec: StreamSpec, frame: VideoFrame) -> list[bytes]:
        img = frame.bgr
        h, w = img.shape[:2]
        if w > spec.max_width:
            scale = spec.max_width / float(w)
            img = cv2.resize(img, (spec.max_width, max(1, int(h * scale))))
            h, w = img.shape[:2]
        ok, buf = cv2.imencode(
            ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), spec.jpeg_quality]
        )
        if not ok:
            raise OSError("jpeg encode failed")
        jpeg = buf.tobytes()
        ts = rtp_timestamp()
        packets, spec.seq = packetize_jpeg(
            jpeg,
            seq_start=spec.seq,
            timestamp=ts,
            ssrc=spec.ssrc,
            width=w,
            height=h,
        )
        return packets
