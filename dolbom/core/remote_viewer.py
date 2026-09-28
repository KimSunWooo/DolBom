"""Read-only bridge from the main server to the existing PyQt screens."""
from __future__ import annotations

import json
import logging
import time
from urllib.parse import urlparse

import cv2
from PyQt6.QtCore import QThread, pyqtSignal
from websockets.sync.client import connect

from dolbom.models import CAM_DISCONNECTED, CAM_PREVIEW, VideoFrame

log = logging.getLogger(__name__)


def server_urls(base: str) -> tuple[str, str]:
    parsed = urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('DOLBOM_VIEWER_URL must be http://HOST:5001')
    root = base.rstrip('/')
    scheme = 'wss' if parsed.scheme == 'https' else 'ws'
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    return root, f'{scheme}://{parsed.hostname}:{port + 1}/ui'


class RemoteVideo(QThread):
    frame_ready = pyqtSignal(object)
    status_changed = pyqtSignal(str, str, str)

    def __init__(self, local_id: str, camera_name: str, base_url: str):
        super().__init__()
        self.local_id = local_id
        self.camera_name = camera_name
        self.url = f'{base_url}/preview/{camera_name}'
        self.running = True
        self.frame_no = 0

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            capture = cv2.VideoCapture(self.url)
            if not capture.isOpened():
                self.status_changed.emit(self.local_id, CAM_DISCONNECTED, '메인 서버 영상에 연결할 수 없습니다.')
                capture.release()
                self.msleep(1500)
                continue
            self.status_changed.emit(self.local_id, CAM_PREVIEW, '메인 서버 영상 수신 중')
            try:
                while self.running:
                    ok, bgr = capture.read()
                    if not ok:
                        break
                    self.frame_no += 1
                    self.frame_ready.emit(VideoFrame(self.local_id, bgr, time.time(), self.frame_no))
            finally:
                capture.release()
            self.status_changed.emit(self.local_id, CAM_DISCONNECTED, '메인 서버 영상 연결 끊김')
            self.msleep(800)


class RemoteResults(QThread):
    result_received = pyqtSignal(dict)
    link_changed = pyqtSignal(str, str)

    def __init__(self, websocket_url: str):
        super().__init__()
        self.url = websocket_url
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            try:
                with connect(self.url, open_timeout=3, close_timeout=1) as socket:
                    self.link_changed.emit('connected', '메인 서버 분석 결과 수신 중')
                    while self.running:
                        try:
                            message = socket.recv(timeout=1)
                        except TimeoutError:
                            continue
                        result = json.loads(message)
                        if isinstance(result, dict):
                            self.result_received.emit(result)
            except Exception as exc:
                log.warning('UI result connection failed: %s', exc)
                self.link_changed.emit('reconnecting', '분석 결과 연결을 다시 시도하는 중')
                self.msleep(1000)
