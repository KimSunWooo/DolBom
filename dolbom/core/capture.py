"""카메라 수집은 QWidget 생명주기와 분리된 QThread에서 수행한다."""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from dolbom.core.demo_frames import make_demo_frame
from dolbom.core.devices import resolve_open_source
from dolbom.models import (
    CAM_DEMO,
    CAM_DISCONNECTED,
    CAM_PREPARING,
    CAM_PREVIEW,
    CAM_RECONNECTING,
    MATCH_MISSING,
    MATCH_UNSET,
    MATCH_UNSTABLE,
    SOURCE_DEMO,
    SOURCE_RTSP,
    Camera,
    VideoFrame,
)

log = logging.getLogger("dolbom.capture")


class CaptureWorker(QThread):
    frame_ready = pyqtSignal(object)
    status_changed = pyqtSignal(str, str, str)  # camera_id, status, detail

    def __init__(self, camera: Camera, demo_forced: bool = False, fps: float = 15.0):
        super().__init__()
        self.camera = camera
        self.demo_forced = demo_forced
        self.fps = fps
        self._running = True
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_no = 0
        self._fail_count = 0
        self._match_detail = ""

    def stop(self) -> None:
        self._running = False

    def update_camera(self, camera: Camera, demo_forced: bool) -> None:
        self.camera = camera
        self.demo_forced = demo_forced

    def _use_demo(self) -> bool:
        if self.demo_forced:
            return True
        if self.camera.source_kind == SOURCE_DEMO:
            return True
        if (self.camera.device_id or "").startswith("demo:"):
            return True
        return False

    def _open_source(self) -> int | str | None:
        source, state, detail = resolve_open_source(self.camera)
        self.camera.match_state = state
        self._match_detail = detail
        return source

    def _open(self) -> bool:
        self._release()
        if self._use_demo():
            return True
        source = self._open_source()
        if source is None or source == "":
            return False
        try:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                return False
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._cap = cap
            return True
        except Exception:
            log.exception("camera open failed id=%s", self.camera.id)
            return False

    def _release(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _read(self) -> Optional[np.ndarray]:
        if self._use_demo():
            self._frame_no += 1
            key = self.camera.source_value
            if (self.camera.device_id or "").startswith("demo:"):
                key = self.camera.device_id.split(":", 1)[-1]
            return make_demo_frame(
                camera_name=self.camera.name,
                location=self.camera.location,
                source_key=key or "warm",
                frame_no=self._frame_no,
            )
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        self._frame_no += 1
        return frame

    def run(self) -> None:
        status = CAM_DEMO if self._use_demo() else CAM_PREPARING
        self.status_changed.emit(self.camera.id, status, "카메라를 여는 중")
        opened = self._open()
        if not opened:
            reason = getattr(self, "_match_detail", "") or "장치에 연결하지 못했습니다"
            if self.camera.match_state in (MATCH_MISSING, MATCH_UNSTABLE, MATCH_UNSET):
                reason = reason or "저장된 장치를 열 수 없습니다. 다시 선택하세요."
            self.status_changed.emit(self.camera.id, CAM_DISCONNECTED, reason)
        else:
            live = CAM_DEMO if self._use_demo() else CAM_PREVIEW
            self.status_changed.emit(self.camera.id, live, "")

        interval = 1.0 / max(5.0, self.fps)
        while self._running:
            started = time.monotonic()
            if not opened:
                self.status_changed.emit(
                    self.camera.id, CAM_RECONNECTING, "재연결을 시도하는 중"
                )
                opened = self._open()
                if opened:
                    live = CAM_DEMO if self._use_demo() else CAM_PREVIEW
                    self.status_changed.emit(self.camera.id, live, "다시 연결됨")
                    self._fail_count = 0
                else:
                    self.status_changed.emit(
                        self.camera.id, CAM_DISCONNECTED, "연결 끊김"
                    )
                    self._sleep_remaining(started, 2.0)
                    continue

            frame = self._read()
            if frame is None:
                self._fail_count += 1
                if self._fail_count >= 8:
                    opened = False
                    self._release()
                    self.status_changed.emit(
                        self.camera.id,
                        CAM_DISCONNECTED,
                        "프레임을 받지 못했습니다",
                    )
                self._sleep_remaining(started, interval)
                continue

            self._fail_count = 0
            vf = VideoFrame(
                camera_id=self.camera.id,
                bgr=frame.copy(),
                captured_at=time.time(),
                frame_no=self._frame_no,
            )
            self.frame_ready.emit(vf)
            self._sleep_remaining(started, interval)

        self._release()

    def _sleep_remaining(self, started: float, interval: float) -> None:
        remain = interval - (time.monotonic() - started)
        if remain > 0:
            self.msleep(int(remain * 1000))
