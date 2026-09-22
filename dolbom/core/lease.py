"""순수 점유 규칙. UI/Qt 없이 검증 가능하다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Occupancy:
    camera_id: str
    owner: str  # exercise | gait
    session_id: str


class CameraLease:
    """운동·보행은 동시에 하나의 세션만 허용한다."""

    def __init__(self) -> None:
        self._current: Optional[Occupancy] = None

    @property
    def current(self) -> Optional[Occupancy]:
        return self._current

    def can_start(self, camera_id: str, owner: str) -> tuple[bool, str]:
        if self._current is None:
            return True, ""
        if self._current.owner == owner and self._current.camera_id == camera_id:
            return False, "이미 이 카메라로 세션이 전송 중입니다."
        label = "운동" if self._current.owner == "exercise" else "보행"
        return (
            False,
            f"진행 중인 {label} 세션을 먼저 종료해야 합니다. 메뉴만 바꿔서는 세션이 끝나지 않습니다.",
        )

    def acquire(self, camera_id: str, owner: str, session_id: str) -> Occupancy:
        ok, reason = self.can_start(camera_id, owner)
        if not ok:
            raise RuntimeError(reason)
        self._current = Occupancy(camera_id=camera_id, owner=owner, session_id=session_id)
        return self._current

    def release(self, session_id: str | None = None) -> None:
        if session_id and self._current and self._current.session_id != session_id:
            return
        self._current = None

    def holds(self, owner: str) -> bool:
        return self._current is not None and self._current.owner == owner
