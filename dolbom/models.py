from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


SOURCE_DEMO = "demo"
SOURCE_DEVICE = "device"
SOURCE_RTSP = "rtsp"

PLAYLIST_LOCAL = "local"
PLAYLIST_HTTPS = "https"

MEDIA_OK = "ok"
MEDIA_MISSING_FILE = "missing_file"
MEDIA_UNSUPPORTED_URL = "unsupported_url"
MEDIA_WEBPAGE = "webpage"
MEDIA_NETWORK = "network"
MEDIA_UNKNOWN = "unknown"

MODE_CCTV = "cctv"
MODE_EXERCISE = "exercise"
MODE_GAIT = "gait"

MSG_URGENT = "urgent"
MSG_CAMERA_ERROR = "camera_error"
MSG_SERVER_ERROR = "server_error"
MSG_INFO = "info"

CAM_PREPARING = "preparing"
CAM_PREVIEW = "preview"
CAM_SENDING = "sending"
CAM_DISCONNECTED = "disconnected"
CAM_RECONNECTING = "reconnecting"
CAM_DISABLED = "disabled"
CAM_DEMO = "demo"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Camera:
    id: str
    name: str
    location: str
    source_kind: str
    source_value: str
    enabled: bool = True
    sort_order: int = 0

    def display_source(self) -> str:
        if self.source_kind == SOURCE_DEMO:
            return "데모 영상"
        if self.source_kind == SOURCE_DEVICE:
            return f"장치 {self.source_value}"
        if self.source_kind == SOURCE_RTSP:
            return mask_secret(self.source_value)
        return self.source_kind


@dataclass
class Patient:
    id: str
    display_name: str
    room: str = ""


@dataclass
class PlaylistItem:
    id: str
    title: str
    topic: str
    source_kind: str
    path_or_url: str
    description: str = ""
    sort_order: int = 0
    media_status: str = MEDIA_UNKNOWN


@dataclass
class SessionRecord:
    id: str
    mode: str
    camera_id: Optional[str]
    patient_id: Optional[str]
    playlist_item_id: Optional[str]
    title: Optional[str]
    topic: Optional[str]
    started_at: str
    ended_at: Optional[str] = None
    status: str = "running"


@dataclass
class AppMessage:
    event_id: str
    severity: str
    occurred_at: str
    content: str
    camera_id: Optional[str] = None
    location: Optional[str] = None
    acknowledged: bool = False
    is_test: bool = False
    navigate_to: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoFrame:
    camera_id: str
    bgr: Any
    captured_at: float
    frame_no: int


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if "://" in value and "@" in value:
        try:
            prefix, rest = value.split("://", 1)
            creds, host = rest.split("@", 1)
            if ":" in creds:
                user, _pw = creds.split(":", 1)
                return f"{prefix}://{user}:****@{host}"
        except ValueError:
            return value
    return value


SEVERITY_LABELS = {
    MSG_URGENT: "긴급",
    MSG_CAMERA_ERROR: "카메라 오류",
    MSG_SERVER_ERROR: "서버 연결 오류",
    MSG_INFO: "안내",
}

MODE_LABELS = {
    MODE_CCTV: "병실 CCTV",
    MODE_EXERCISE: "운동",
    MODE_GAIT: "보행",
}

CAM_STATUS_LABELS = {
    CAM_PREPARING: "연결 준비 중",
    CAM_PREVIEW: "미리보기 중",
    CAM_SENDING: "서버 전송 중",
    CAM_DISCONNECTED: "연결 끊김",
    CAM_RECONNECTING: "재연결 중",
    CAM_DISABLED: "비활성",
    CAM_DEMO: "데모 영상",
}
