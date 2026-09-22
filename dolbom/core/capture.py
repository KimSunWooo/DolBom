"""카메라 수집은 QWidget 생명주기와 분리된 QThread에서 수행한다."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from dolbom.core.demo_frames import make_demo_frame
from dolbom.core.devices import capture_targets, describe_device_access
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
    Camera,
    VideoFrame,
)

log = logging.getLogger("dolbom.capture")


def open_device_capture(source: str) -> tuple[Optional[cv2.VideoCapture], str, str]:
    """실제 캡처 입력을 연다. 해상도·FPS·FOURCC는 열 때 강제하지 않는다.

    Returns:
        (cap_or_None, backend_name, error_detail)
    """
    if not source:
        return None, "", "캡처 입력이 비어 있습니다."
    if source.startswith("rtsp://") or source.startswith("http://") or source.startswith("https://"):
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG) if hasattr(cv2, "CAP_FFMPEG") else cv2.VideoCapture(source)
        if cap is None or not cap.isOpened():
            return None, "ffmpeg", "네트워크 카메라 주소를 열지 못했습니다."
        return cap, "ffmpeg", ""
    path = source
    if os.path.exists(source):
        path = os.path.realpath(source)
    access = describe_device_access(path) if path.startswith("/dev/") else ""
    if access:
        return None, "", access
    api = getattr(cv2, "CAP_V4L2", None) if path.startswith("/dev/") else None
    if api is not None:
        cap = cv2.VideoCapture(path, api)
        backend = "V4L2"
    else:
        cap = cv2.VideoCapture(path)
        backend = "default"
    if cap is None or not cap.isOpened():
        return None, backend, f"{backend} 백엔드가 장치를 열지 못했습니다 ({path})"
    return cap, backend, ""


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
        self._backend = ""
        self._open_input = ""
        self._got_frame = False

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

    def _open(self) -> bool:
        self._release()
        self._got_frame = False
        if self._use_demo():
            self._backend = "demo"
            self._open_input = self.camera.device_id or self.camera.source_value or "demo"
            log.info(
                "capture open demo camera=%s name=%s input=%s demo_forced=%s",
                self.camera.id,
                self.camera.name,
                self._open_input,
                self.demo_forced,
            )
            return True
        targets, state, detail = capture_targets(self.camera)
        self.camera.match_state = state
        self._match_detail = detail
        if not targets:
            log.info(
                "capture open skipped camera=%s name=%s reason=%s",
                self.camera.id,
                self.camera.name,
                detail or "no capture target",
            )
            return False
        last_err = detail
        for source in targets:
            log.info(
                "capture opening camera=%s name=%s input=%s stable_id=%s",
                self.camera.id,
                self.camera.name,
                source,
                self.camera.device_id,
            )
            cap, backend, err = open_device_capture(source)
            self._backend = backend
            self._open_input = source
            if cap is None:
                last_err = err or last_err
                log.info("capture open failed camera=%s input=%s err=%s", self.camera.id, source, err)
                continue
            self._cap = cap
            log.info(
                "capture open ok camera=%s input=%s backend=%s (waiting first frame)",
                self.camera.id,
                source,
                backend,
            )
            return True
        self._match_detail = last_err or self._match_detail
        return False

    def _try_mjpeg(self) -> None:
        if self._cap is None:
            return
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        ok = self._cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        log.info("capture try MJPEG camera=%s set=%s", self.camera.id, ok)

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
        if not ok or frame is None or getattr(frame, "size", 0) == 0:
            return None
        self._frame_no += 1
        return frame

    def run(self) -> None:
        log.info(
            "capture thread start camera=%s name=%s kind=%s",
            self.camera.id,
            self.camera.name,
            self.camera.source_kind,
        )
        self.status_changed.emit(self.camera.id, CAM_PREPARING, "연결 중")
        opened = self._open()
        if not opened:
            reason = self._match_detail or "장치에 연결하지 못했습니다"
            if self.camera.match_state in (MATCH_MISSING, MATCH_UNSTABLE, MATCH_UNSET):
                reason = self._match_detail or "저장된 장치를 열 수 없습니다. 다시 선택하세요."
            self.status_changed.emit(self.camera.id, CAM_DISCONNECTED, reason)
        elif self._use_demo():
            self.status_changed.emit(self.camera.id, CAM_DEMO, "데모 영상")
        else:
            self.status_changed.emit(self.camera.id, CAM_PREPARING, "연결 중 · 첫 프레임을 기다리는 중")

        interval = 1.0 / max(5.0, self.fps)
        backoff = 2.0
        mjpeg_tried = False
        while self._running:
            started = time.monotonic()
            if not opened:
                self.status_changed.emit(
                    self.camera.id, CAM_RECONNECTING, "재연결을 시도하는 중"
                )
                opened = self._open()
                mjpeg_tried = False
                if opened:
                    self._fail_count = 0
                    if self._use_demo():
                        self.status_changed.emit(self.camera.id, CAM_DEMO, "데모 영상")
                    else:
                        self.status_changed.emit(
                            self.camera.id, CAM_PREPARING, "연결 중 · 첫 프레임을 기다리는 중"
                        )
                    backoff = 2.0
                else:
                    self.status_changed.emit(
                        self.camera.id,
                        CAM_DISCONNECTED,
                        self._match_detail or "연결 끊김",
                    )
                    self._sleep_remaining(started, backoff)
                    backoff = min(5.0, backoff + 1.0)
                    continue

            frame = self._read()
            if frame is None:
                self._fail_count += 1
                if opened and not self._use_demo() and self._fail_count == 4 and not mjpeg_tried:
                    mjpeg_tried = True
                    self._try_mjpeg()
                if self._fail_count >= 8:
                    reason = "열기는 됐지만 프레임을 받지 못했습니다"
                    if self._open_input:
                        reason = f"{reason} ({self._open_input}, {self._backend or 'backend?'})"
                    log.info(
                        "capture read failed camera=%s input=%s backend=%s count=%s",
                        self.camera.id,
                        self._open_input,
                        self._backend,
                        self._fail_count,
                    )
                    opened = False
                    self._release()
                    self.status_changed.emit(self.camera.id, CAM_DISCONNECTED, reason)
                self._sleep_remaining(started, interval)
                continue

            if not self._got_frame:
                self._got_frame = True
                h, w = frame.shape[:2]
                log.info(
                    "capture first frame camera=%s input=%s backend=%s size=%sx%s",
                    self.camera.id,
                    self._open_input,
                    self._backend,
                    w,
                    h,
                )
                if not self._use_demo():
                    self.status_changed.emit(self.camera.id, CAM_PREVIEW, f"{w}x{h}")
            self._fail_count = 0
            backoff = 2.0
            vf = VideoFrame(
                camera_id=self.camera.id,
                bgr=np.ascontiguousarray(frame.copy()),
                captured_at=time.time(),
                frame_no=self._frame_no,
            )
            self.frame_ready.emit(vf)
            self._sleep_remaining(started, interval)

        self._release()
        log.info("capture thread stop camera=%s name=%s", self.camera.id, self.camera.name)

    def _sleep_remaining(self, started: float, interval: float) -> None:
        remain = interval - (time.monotonic() - started)
        if remain > 0:
            self.msleep(int(remain * 1000))
