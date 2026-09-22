"""카메라 수명·최신 프레임 버스. 페이지가 사라져도 수집은 유지된다."""

from __future__ import annotations

import logging
import time
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from dolbom.core.capture import CaptureWorker
from dolbom.db.store import Store
from dolbom.models import CAM_DISABLED, CAM_PREPARING, Camera, VideoFrame

log = logging.getLogger("dolbom.cameras")


class CameraHub(QObject):
    frame_ready = pyqtSignal(object)  # VideoFrame
    status_changed = pyqtSignal(str, str, str)  # id, status, detail

    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self._workers: dict[str, CaptureWorker] = {}
        self._latest: dict[str, VideoFrame] = {}
        self._status: dict[str, tuple[str, str, float]] = {}
        self._demo_forced = store.demo_mode()

    def set_demo_forced(self, value: bool) -> None:
        if self._demo_forced == value:
            return
        self._demo_forced = value
        self.restart_all()

    def demo_forced(self) -> bool:
        return self._demo_forced

    def latest(self, camera_id: str) -> Optional[VideoFrame]:
        return self._latest.get(camera_id)

    def last_status(self, camera_id: str) -> tuple[str, str, float]:
        return self._status.get(camera_id, (CAM_PREPARING, "", 0.0))

    def is_running(self, camera_id: str) -> bool:
        w = self._workers.get(camera_id)
        return bool(w and w.isRunning())

    def ensure_running(self, camera: Camera) -> None:
        if not camera.enabled:
            self.stop_one(camera.id)
            self.status_changed.emit(camera.id, CAM_DISABLED, "비활성화됨")
            return
        existing = self._workers.get(camera.id)
        if existing and existing.isRunning():
            existing.update_camera(camera, self._demo_forced)
            return
        self._start_worker(camera)

    def _start_worker(self, camera: Camera) -> None:
        self.stop_one(camera.id)
        worker = CaptureWorker(camera, demo_forced=self._demo_forced)
        worker.frame_ready.connect(self._on_frame)
        worker.status_changed.connect(self._on_status)
        self._workers[camera.id] = worker
        worker.start()

    def _on_frame(self, frame: VideoFrame) -> None:
        self._latest[frame.camera_id] = frame
        self.frame_ready.emit(frame)

    def _on_status(self, camera_id: str, status: str, detail: str) -> None:
        self._status[camera_id] = (status, detail, time.time())
        self.status_changed.emit(camera_id, status, detail)

    def stop_one(self, camera_id: str) -> None:
        worker = self._workers.pop(camera_id, None)
        if worker is None:
            return
        worker.stop()
        if not worker.wait(2500):
            log.warning("capture thread did not stop in time id=%s", camera_id)
            worker.terminate()
            worker.wait(800)

    def start_enabled(self) -> None:
        for cam in self.store.list_cameras():
            self.ensure_running(cam)

    def restart_all(self) -> None:
        self.stop_all()
        self.start_enabled()

    def reload_camera(self, camera_id: str) -> None:
        cam = self.store.get_camera(camera_id)
        if cam is None:
            self.stop_one(camera_id)
            self._latest.pop(camera_id, None)
            return
        self.ensure_running(cam)

    def stop_all(self) -> None:
        ids = list(self._workers.keys())
        for camera_id in ids:
            self.stop_one(camera_id)
