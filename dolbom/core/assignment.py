"""카메라 용도 할당. 같은 물리 장치 중복 지정을 막는다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dolbom.core.devices import _id_match
from dolbom.models import ROLE_CLINICAL, Camera


@dataclass
class AssignmentConflict:
    other: Camera
    message: str


def device_key(cam: Camera) -> str:
    if cam.device_id:
        return cam.device_id
    if cam.source_kind == "rtsp":
        return f"rtsp:{cam.source_value}"
    if cam.source_kind == "demo":
        return f"demo:{cam.source_value}"
    return ""


def conflict_for(cameras: list[Camera], camera_id: str, key: str) -> Optional[AssignmentConflict]:
    if not key:
        return None
    for cam in cameras:
        if cam.id == camera_id or not cam.enabled:
            continue
        if _id_match(device_key(cam), key) or device_key(cam) == key:
            return AssignmentConflict(
                other=cam,
                message=(
                    f"이 장치는 이미 ‘{cam.role_text()}’({cam.name})에 할당되어 있습니다. "
                    "같은 장치를 두 용도에 동시에 지정할 수 없습니다."
                ),
            )
    return None


def clinical_camera(cameras: list[Camera]) -> Optional[Camera]:
    for cam in cameras:
        if cam.role == ROLE_CLINICAL:
            return cam
    return None


def cctv_cameras(cameras: list[Camera]) -> list[Camera]:
    return [c for c in cameras if c.role.startswith("cctv_")]
