"""운동·보행·CCTV 전송 세션. 메뉴 전환만으로 종료하지 않는다."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from dolbom.core.lease import CameraLease
from dolbom.core.sender import StreamSender, StreamSpec, ssrc_from
from dolbom.db.store import Store
from dolbom.models import (
    MODE_CCTV,
    MODE_EXERCISE,
    MODE_GAIT,
    SessionRecord,
    now_iso,
)
from dolbom import protocol as proto

log = logging.getLogger("dolbom.session")


@dataclass
class LiveSession:
    session_id: str
    stream_id: str
    mode: str
    camera_id: str
    patient_id: Optional[str]
    playlist_item_id: Optional[str]
    title: Optional[str]
    topic: Optional[str]
    started_at: str
    started_mono: float


class SessionManager(QObject):
    session_changed = pyqtSignal()
    notice = pyqtSignal(str)

    def __init__(self, store: Store, sender: StreamSender, control):
        super().__init__()
        self.store = store
        self.sender = sender
        self.control = control
        self.lease = CameraLease()
        self._live: dict[str, LiveSession] = {}  # session_id ->
        self._cctv: dict[str, LiveSession] = {}  # camera_id ->

    def clinical(self) -> Optional[LiveSession]:
        occ = self.lease.current
        if occ is None:
            return None
        return self._live.get(occ.session_id)

    def cctv_session(self, camera_id: str) -> Optional[LiveSession]:
        return self._cctv.get(camera_id)

    def is_sending_camera(self, camera_id: str) -> bool:
        if camera_id in self._cctv:
            return True
        live = self.clinical()
        return bool(live and live.camera_id == camera_id)

    def active_payloads(self) -> list[dict]:
        items = list(self._live.values()) + list(self._cctv.values())
        return [
            {
                "session_id": s.session_id,
                "stream_id": s.stream_id,
                "mode": s.mode,
                "camera_id": s.camera_id,
                "patient_id": s.patient_id,
                "playlist_item_id": s.playlist_item_id,
                "title": s.title,
                "topic": s.topic,
                "started_at": s.started_at,
            }
            for s in items
        ]

    def start_clinical(
        self,
        *,
        mode: str,
        camera_id: str,
        patient_id: Optional[str],
        playlist_item_id: Optional[str],
        title: Optional[str],
        topic: Optional[str],
    ) -> tuple[bool, str, Optional[LiveSession]]:
        if mode not in (MODE_EXERCISE, MODE_GAIT):
            return False, "지원하지 않는 촬영 모드입니다.", None
        ok, reason = self.lease.can_start(camera_id, mode)
        if not ok:
            return False, reason, None
        session_id = str(uuid.uuid4())
        stream_id = f"{mode}:{camera_id}:{session_id[:8]}"
        started = now_iso()
        live = LiveSession(
            session_id=session_id,
            stream_id=stream_id,
            mode=mode,
            camera_id=camera_id,
            patient_id=patient_id,
            playlist_item_id=playlist_item_id,
            title=title,
            topic=topic,
            started_at=started,
            started_mono=__import__("time").monotonic(),
        )
        self.lease.acquire(camera_id, mode, session_id)
        self._live[session_id] = live
        self.store.insert_session(
            SessionRecord(
                id=session_id,
                mode=mode,
                camera_id=camera_id,
                patient_id=patient_id,
                playlist_item_id=playlist_item_id,
                title=title,
                topic=topic,
                started_at=started,
                status="sending",
            )
        )
        self.sender.upsert(
            StreamSpec(
                camera_id=camera_id,
                stream_id=stream_id,
                session_id=session_id,
                mode=mode,
                ssrc=ssrc_from(stream_id),
                max_width=480,
            )
        )
        self.control.send(
            proto.session_start(
                session_id=session_id,
                stream_id=stream_id,
                mode=mode,
                camera_id=camera_id,
                patient_id=patient_id,
                playlist_item_id=playlist_item_id,
                title=title,
                topic=topic,
                started_at=started,
            )
        )
        self.session_changed.emit()
        return True, "전송을 시작했습니다.", live

    def end_clinical(self, reason: str = "ended") -> Optional[LiveSession]:
        live = self.clinical()
        if live is None:
            return None
        self._finish(live, reason)
        self.lease.release(live.session_id)
        self._live.pop(live.session_id, None)
        self.session_changed.emit()
        return live

    def start_cctv(self, camera_id: str) -> tuple[bool, str]:
        if camera_id in self._cctv:
            return True, "이미 전송 중입니다."
        session_id = str(uuid.uuid4())
        stream_id = f"cctv:{camera_id}:{session_id[:8]}"
        started = now_iso()
        live = LiveSession(
            session_id=session_id,
            stream_id=stream_id,
            mode=MODE_CCTV,
            camera_id=camera_id,
            patient_id=None,
            playlist_item_id=None,
            title=None,
            topic=None,
            started_at=started,
            started_mono=__import__("time").monotonic(),
        )
        self._cctv[camera_id] = live
        self.store.insert_session(
            SessionRecord(
                id=session_id,
                mode=MODE_CCTV,
                camera_id=camera_id,
                patient_id=None,
                playlist_item_id=None,
                title=None,
                topic=None,
                started_at=started,
                status="sending",
            )
        )
        self.sender.upsert(
            StreamSpec(
                camera_id=camera_id,
                stream_id=stream_id,
                session_id=session_id,
                mode=MODE_CCTV,
                ssrc=ssrc_from(stream_id),
                max_width=320,
            )
        )
        self.control.send(
            proto.session_start(
                session_id=session_id,
                stream_id=stream_id,
                mode=MODE_CCTV,
                camera_id=camera_id,
                patient_id=None,
                playlist_item_id=None,
                title=None,
                topic=None,
                started_at=started,
            )
        )
        self.session_changed.emit()
        return True, "CCTV 전송을 시작했습니다."

    def end_cctv(self, camera_id: str) -> None:
        live = self._cctv.pop(camera_id, None)
        if live:
            self._finish(live, "ended")
            self.session_changed.emit()

    def end_all(self) -> list[str]:
        names = []
        if self.clinical():
            mode = self.clinical().mode
            names.append("운동" if mode == MODE_EXERCISE else "보행")
            self.end_clinical("app_exit")
        for camera_id in list(self._cctv.keys()):
            names.append("CCTV 전송")
            self.end_cctv(camera_id)
        return names

    def _finish(self, live: LiveSession, reason: str) -> None:
        ended = now_iso()
        self.sender.remove_session(live.session_id)
        self.store.end_session(live.session_id, ended, reason)
        self.control.send(proto.session_end(live.session_id, ended))
