"""
메인 서버 제어 채널 초안 (draft).

기존 서버 규격이 없어 클라이언트가 사용하는 최소 메시지 형식을 분리해 둔다.
이 모듈이 채워져 있어도 '실제 메인 서버 연동 완료'를 의미하지 않는다.

전송 형식: TCP, 4바이트 big-endian 길이 + UTF-8 JSON 본문.
한 JSON 객체가 한 메시지이다. 메시지 경계는 길이 접두사로만 구분한다.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Optional

PROTOCOL_VERSION = 1
PROTOCOL_STATUS = "draft"

MSG_HELLO = "hello"
MSG_HELLO_ACK = "hello.ack"
MSG_PING = "ping"
MSG_PONG = "pong"
MSG_SESSION_START = "session.start"
MSG_SESSION_END = "session.end"
MSG_STATUS = "status"
MSG_SYNC_REQUEST = "sync.request"
MSG_SYNC = "session.sync"
MSG_EVENT = "event"
MSG_ERROR = "error"


class ProtocolError(Exception):
    pass


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return struct.pack("!I", len(body)) + body


def try_decode(buffer: bytearray) -> tuple[Optional[dict[str, Any]], bytearray]:
    """버퍼에서 메시지 0~1개를 꺼낸다. 불완전하면 (None, 원본버퍼)."""
    if len(buffer) < 4:
        return None, buffer
    (length,) = struct.unpack("!I", bytes(buffer[:4]))
    if length > 2_000_000:
        raise ProtocolError(f"message too large: {length}")
    if len(buffer) < 4 + length:
        return None, buffer
    body = bytes(buffer[4 : 4 + length])
    rest = bytearray(buffer[4 + length :])
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be a JSON object")
    return payload, rest


def hello(client_id: str) -> dict[str, Any]:
    return {
        "type": MSG_HELLO,
        "client_id": client_id,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_status": PROTOCOL_STATUS,
    }


def session_start(
    *,
    session_id: str,
    stream_id: str,
    mode: str,
    camera_id: str,
    patient_id: Optional[str],
    playlist_item_id: Optional[str],
    title: Optional[str],
    topic: Optional[str],
    started_at: str,
) -> dict[str, Any]:
    return {
        "type": MSG_SESSION_START,
        "session_id": session_id,
        "stream_id": stream_id,
        "mode": mode,
        "camera_id": camera_id,
        "patient_id": patient_id,
        "playlist_item_id": playlist_item_id,
        "title": title,
        "topic": topic,
        "started_at": started_at,
        "protocol_version": PROTOCOL_VERSION,
    }


def session_end(session_id: str, ended_at: str) -> dict[str, Any]:
    return {
        "type": MSG_SESSION_END,
        "session_id": session_id,
        "ended_at": ended_at,
    }


def status_update(payload: dict[str, Any]) -> dict[str, Any]:
    out = {"type": MSG_STATUS, **payload}
    return out


def sync_request(active_sessions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": MSG_SYNC_REQUEST,
        "active_sessions": active_sessions,
    }
