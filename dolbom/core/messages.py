"""공통 알림. 시험 메시지는 실제 긴급 이벤트와 분리해 저장한다."""

from __future__ import annotations

import uuid
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from dolbom.db.store import Store
from dolbom.models import (
    MSG_CAMERA_ERROR,
    MSG_INFO,
    MSG_SERVER_ERROR,
    MSG_URGENT,
    AppMessage,
    now_iso,
)
from dolbom import protocol as proto


class MessageCenter(QObject):
    changed = pyqtSignal()
    urgent = pyqtSignal(object)

    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self._sound = True

    def set_sound(self, enabled: bool) -> None:
        self._sound = enabled

    def unread(self) -> int:
        return self.store.unread_count()

    def latest(self) -> Optional[AppMessage]:
        items = self.store.list_messages(limit=1)
        return items[0] if items else None

    def add(
        self,
        *,
        severity: str,
        content: str,
        camera_id: Optional[str] = None,
        location: Optional[str] = None,
        navigate_to: Optional[str] = None,
        is_test: bool = False,
        event_id: Optional[str] = None,
        occurred_at: Optional[str] = None,
    ) -> bool:
        msg = AppMessage(
            event_id=event_id or str(uuid.uuid4()),
            severity=severity,
            occurred_at=occurred_at or now_iso(),
            content=content,
            camera_id=camera_id,
            location=location,
            is_test=is_test,
            navigate_to=navigate_to,
        )
        inserted = self.store.upsert_message(msg)
        if not inserted:
            return False
        self.changed.emit()
        if severity == MSG_URGENT:
            self.urgent.emit(msg)
            if self._sound and not is_test:
                QApplication.beep()
            elif self._sound and is_test:
                QApplication.beep()
        return True

    def from_server(self, payload: dict) -> None:
        if payload.get("type") != proto.MSG_EVENT:
            return
        severity = payload.get("severity") or MSG_INFO
        if severity not in (MSG_URGENT, MSG_CAMERA_ERROR, MSG_SERVER_ERROR, MSG_INFO):
            severity = MSG_INFO
        is_test = bool(payload.get("is_test") or payload.get("test"))
        content = str(payload.get("content") or payload.get("message") or "서버 메시지")
        if is_test and not content.startswith("[시험]"):
            content = f"[시험] {content}"
        # 신원이 확인되지 않은 서버 이벤트에 환자를 붙이지 않는다.
        self.add(
            severity=severity,
            content=content,
            camera_id=payload.get("camera_id"),
            location=payload.get("location"),
            navigate_to=payload.get("navigate_to"),
            is_test=is_test,
            event_id=str(payload.get("event_id") or uuid.uuid4()),
            occurred_at=payload.get("occurred_at"),
        )

    def ack(self, event_id: str) -> None:
        self.store.acknowledge(event_id)
        self.changed.emit()

    def ack_all(self) -> None:
        self.store.acknowledge_all()
        self.changed.emit()

    def inject_test(self, severity: str = MSG_INFO) -> None:
        labels = {
            MSG_URGENT: "시험용 긴급 알림입니다. 실제 낙상·응급 이벤트가 아닙니다.",
            MSG_CAMERA_ERROR: "시험용 카메라 오류 메시지입니다.",
            MSG_SERVER_ERROR: "시험용 서버 연결 오류 메시지입니다.",
            MSG_INFO: "시험용 안내 메시지입니다.",
        }
        nav = {
            MSG_URGENT: "cctv",
            MSG_CAMERA_ERROR: "cctv",
            MSG_SERVER_ERROR: "settings",
            MSG_INFO: "exercise",
        }
        self.add(
            severity=severity,
            content=labels.get(severity, "시험 메시지"),
            navigate_to=nav.get(severity),
            is_test=True,
        )
