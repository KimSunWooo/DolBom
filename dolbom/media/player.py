"""표준 영상 재생. 로컬은 OpenCV 스레드, HTTPS 직접 미디어는 Qt Multimedia."""

from __future__ import annotations

import logging
import os
import time
from urllib.parse import urlparse

import cv2
from PyQt6.QtCore import QObject, QThread, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

from dolbom.models import (
    MEDIA_MISSING_FILE,
    MEDIA_NETWORK,
    MEDIA_OK,
    MEDIA_UNKNOWN,
    MEDIA_UNSUPPORTED_URL,
    MEDIA_WEBPAGE,
    PLAYLIST_HTTPS,
    PLAYLIST_LOCAL,
    PlaylistItem,
)

log = logging.getLogger("dolbom.player")

WEBPAGE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
    "physitrack.com",
    "www.physitrack.com",
    "vimeo.com",
    "www.vimeo.com",
)


def classify_item(item: PlaylistItem) -> str:
    if item.source_kind == PLAYLIST_LOCAL:
        if os.path.isfile(item.path_or_url):
            return MEDIA_OK
        return MEDIA_MISSING_FILE
    url = item.path_or_url.strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return MEDIA_UNSUPPORTED_URL
    if host in WEBPAGE_HOSTS or host.endswith(".youtube.com"):
        return MEDIA_WEBPAGE
    path = (parsed.path or "").lower()
    media_ext = (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".avi", ".mp3", ".m3u8")
    if any(path.endswith(ext) for ext in media_ext):
        return MEDIA_OK
    return MEDIA_WEBPAGE


def status_reason(status: str) -> str:
    return {
        MEDIA_OK: "내부 플레이어로 재생할 수 있습니다.",
        MEDIA_MISSING_FILE: "로컬 영상 파일을 찾을 수 없습니다. 파일이 이동·삭제되었을 수 있습니다.",
        MEDIA_WEBPAGE: "유튜브·일반 웹페이지 주소는 내부 재생을 보장하지 않습니다.",
        MEDIA_UNSUPPORTED_URL: "지원하지 않는 주소 형식입니다. HTTPS 직접 미디어 주소만 내부 재생을 시도합니다.",
        MEDIA_NETWORK: "네트워크를 확인하는 중이거나 응답이 없습니다.",
        MEDIA_UNKNOWN: "재생 가능 여부를 아직 확인하지 않았습니다.",
    }.get(status, "")


class _LocalPlayThread(QThread):
    frame_ready = pyqtSignal(object)
    position = pyqtSignal(int, int)  # ms, duration
    finished_naturally = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._path = ""
        self._running = True
        self._playing = False
        self._loop = False
        self._seek = -1
        self._cap = None

    def set_source(self, path: str) -> None:
        self._path = path
        self._playing = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def play(self) -> None:
        self._playing = True

    def pause(self) -> None:
        self._playing = False

    def set_loop(self, loop: bool) -> None:
        self._loop = loop

    def seek_ratio(self, ratio: float) -> None:
        self._seek = max(0.0, min(1.0, ratio))

    def stop_thread(self) -> None:
        self._running = False
        self._playing = False

    def run(self) -> None:
        while self._running:
            if not self._path:
                self.msleep(40)
                continue
            if self._cap is None:
                cap = cv2.VideoCapture(self._path)
                if not cap.isOpened():
                    self.failed.emit("영상을 열 수 없습니다.")
                    self._path = ""
                    continue
                self._cap = cap
            fps = self._cap.get(cv2.CAP_PROP_FPS) or 12.0
            frame_count = self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1
            delay = max(8, int(1000 / max(1.0, fps)))
            if self._seek >= 0:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, int(self._seek * frame_count))
                self._seek = -1
            if not self._playing:
                self.msleep(40)
                continue
            ok, frame = self._cap.read()
            if not ok or frame is None:
                if self._loop:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self._playing = False
                self.finished_naturally.emit()
                self.msleep(40)
                continue
            pos = int(self._cap.get(cv2.CAP_PROP_POS_MSEC) or 0)
            duration = int((frame_count / max(1.0, fps)) * 1000)
            self.frame_ready.emit(frame.copy())
            self.position.emit(pos, duration)
            self.msleep(delay)
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class StandardPlayer(QObject):
    """UI는 시그널만 구독한다. 네트워크/디코드는 작업 스레드."""

    frame_ready = pyqtSignal(object)
    status_text = pyqtSignal(str)
    can_open_external = pyqtSignal(str)
    position = pyqtSignal(int, int)
    playing_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._item: PlaylistItem | None = None
        self._local = _LocalPlayThread()
        self._local.frame_ready.connect(self.frame_ready.emit)
        self._local.position.connect(self.position.emit)
        self._local.failed.connect(self._on_local_fail)
        self._local.start()
        self._remote = QMediaPlayer()
        self._audio = QAudioOutput()
        self._remote.setAudioOutput(self._audio)
        self._remote.errorOccurred.connect(self._on_remote_error)
        self._remote.playbackStateChanged.connect(self._on_remote_state)
        self._remote.positionChanged.connect(self._on_remote_pos)
        self._using_remote = False
        self._loop = False

    def shutdown(self) -> None:
        self._local.stop_thread()
        self._remote.stop()
        if not self._local.wait(1500):
            self._local.terminate()

    def set_loop(self, loop: bool) -> None:
        self._loop = loop
        self._local.set_loop(loop)
        self._remote.setLoops(
            QMediaPlayer.Loops.Infinite if loop else QMediaPlayer.Loops.Once
        )

    def load(self, item: PlaylistItem) -> str:
        self.stop()
        self._item = item
        status = classify_item(item)
        if status == MEDIA_MISSING_FILE:
            self.status_text.emit(status_reason(status))
            self.can_open_external.emit("")
            return status
        if status in (MEDIA_WEBPAGE, MEDIA_UNSUPPORTED_URL):
            self.status_text.emit(status_reason(status))
            self.can_open_external.emit(item.path_or_url)
            return status
        if item.source_kind == PLAYLIST_LOCAL:
            self._using_remote = False
            self._local.set_source(item.path_or_url)
            self.status_text.emit("로컬 영상을 불러왔습니다. 재생을 누르면 시작합니다.")
            self.can_open_external.emit("")
            return MEDIA_OK
        self._using_remote = True
        self.status_text.emit("온라인 영상을 준비하는 중…")
        self._remote.setSource(QUrl(item.path_or_url))
        self.can_open_external.emit(item.path_or_url)
        return MEDIA_OK

    def play(self) -> None:
        if self._item is None:
            return
        if self._using_remote:
            self._remote.play()
        else:
            self._local.play()
            self.playing_changed.emit(True)

    def pause(self) -> None:
        if self._using_remote:
            self._remote.pause()
        else:
            self._local.pause()
            self.playing_changed.emit(False)

    def stop(self) -> None:
        self._local.pause()
        self._local.set_source("")
        self._remote.stop()
        self.playing_changed.emit(False)

    def seek_ratio(self, ratio: float) -> None:
        if self._using_remote:
            duration = max(1, int(self._remote.duration()))
            self._remote.setPosition(int(duration * ratio))
        else:
            self._local.seek_ratio(ratio)

    def _on_local_fail(self, msg: str) -> None:
        self.status_text.emit(msg)
        self.playing_changed.emit(False)

    def _on_remote_error(self, error, text: str) -> None:
        reason = text or "내부 플레이어가 이 주소를 재생하지 못했습니다."
        self.status_text.emit(reason + " 브라우저에서 열 수 있습니다.")
        if self._item:
            self.can_open_external.emit(self._item.path_or_url)

    def _on_remote_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playing_changed.emit(playing)
        if playing:
            self.status_text.emit("온라인 영상을 재생 중입니다.")

    def _on_remote_pos(self, pos: int) -> None:
        self.position.emit(int(pos), int(self._remote.duration()))
