"""로컬 카메라 열거. 엔드포인트 수 ≠ 물리 카메라 수를 고려해 묶는다."""

from __future__ import annotations

import glob
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

from dolbom.models import SOURCE_DEMO

log = logging.getLogger("dolbom.devices")

KIND_LOCAL = "local"
KIND_DEMO = "demo"

_ENUM_LOCK = threading.Lock()
_ENUM_CACHE: tuple[float, list] = (0.0, [])
_ENUM_TTL = 1.5


@dataclass
class Endpoint:
    index: int
    path: str
    name: str
    bus_info: str = ""
    parent: str = ""
    by_id: str = ""
    by_path: str = ""
    is_capture: bool = True
    is_metadata: bool = False


@dataclass
class PhysicalDevice:
    stable_id: str
    display_name: str
    index: int
    open_path: str
    kind: str = KIND_LOCAL
    bus_info: str = ""
    unique: bool = True
    connected: bool = True
    endpoint_count: int = 1
    extra_note: str = ""
    aliases: list[str] = field(default_factory=list)

    def distinguish_label(self) -> str:
        ident = self.stable_id
        if len(ident) > 42:
            ident = "…" + ident[-40:]
        bits = [self.display_name, ident]
        if self.bus_info:
            bits.append(self.bus_info)
        if self.endpoint_count > 1:
            bits.append(f"노드 {self.endpoint_count}개")
        return " · ".join(bits)


DEMO_DEVICES = [
    PhysicalDevice(
        stable_id="demo:warm",
        display_name="데모 카메라 A",
        index=-1,
        open_path="demo:warm",
        kind=KIND_DEMO,
        unique=True,
        extra_note="개발용 합성 영상 · 실제 카메라 아님",
    ),
    PhysicalDevice(
        stable_id="demo:cool",
        display_name="데모 카메라 B",
        index=-1,
        open_path="demo:cool",
        kind=KIND_DEMO,
        unique=True,
        extra_note="개발용 합성 영상 · 실제 카메라 아님",
    ),
    PhysicalDevice(
        stable_id="demo:green",
        display_name="데모 카메라 C",
        index=-1,
        open_path="demo:green",
        kind=KIND_DEMO,
        unique=True,
        extra_note="개발용 합성 영상 · 실제 카메라 아님",
    ),
    PhysicalDevice(
        stable_id="demo:purple",
        display_name="데모 카메라 D",
        index=-1,
        open_path="demo:purple",
        kind=KIND_DEMO,
        unique=True,
        extra_note="개발용 합성 영상 · 실제 카메라 아님",
    ),
]


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _v4l_maps() -> tuple[dict[str, str], dict[str, str]]:
    by_id: dict[str, str] = {}
    by_path: dict[str, str] = {}
    for link in glob.glob("/dev/v4l/by-id/*"):
        try:
            by_id[os.path.realpath(link)] = os.path.basename(link)
        except OSError:
            continue
    for link in glob.glob("/dev/v4l/by-path/*"):
        try:
            by_path[os.path.realpath(link)] = os.path.basename(link)
        except OSError:
            continue
    return by_id, by_path


def _query_capture(path: str) -> tuple[Optional[bool], str, str]:
    """(is_capture, card_name, bus_info). ioctl 실패 시 is_capture=None."""
    name = ""
    bus = ""
    try:
        import ctypes
        import fcntl

        class cap(ctypes.Structure):
            _fields_ = [
                ("driver", ctypes.c_char * 16),
                ("card", ctypes.c_char * 32),
                ("bus_info", ctypes.c_char * 32),
                ("version", ctypes.c_uint32),
                ("capabilities", ctypes.c_uint32),
                ("device_caps", ctypes.c_uint32),
                ("reserved", ctypes.c_uint32 * 3),
            ]

        V4L2_CAP_VIDEO_CAPTURE = 0x00000001
        V4L2_CAP_VIDEO_CAPTURE_MPLANE = 0x00001000
        V4L2_CAP_META_CAPTURE = 0x00800000
        # _IOWR('V', 0, struct v4l2_capability) — 64-bit Linux, size 104
        VIDIOC_QUERYCAP = 0xC0685600
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            c = cap()
            fcntl.ioctl(fd, VIDIOC_QUERYCAP, c)
            name = c.card.decode("utf-8", "ignore").strip()
            bus = c.bus_info.decode("utf-8", "ignore").strip()
            flags = c.device_caps or c.capabilities
            meta_only = bool(flags & V4L2_CAP_META_CAPTURE) and not (
                flags & (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_CAPTURE_MPLANE)
            )
            is_cap = bool(flags & (V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_VIDEO_CAPTURE_MPLANE))
            if meta_only:
                is_cap = False
            return is_cap, name, bus
        finally:
            os.close(fd)
    except OSError as exc:
        log.info("v4l querycap failed path=%s err=%s", path, exc)
        return None, name, bus
    except Exception:
        log.info("v4l querycap failed path=%s", path, exc_info=True)
        return None, name, bus


def list_linux_endpoints() -> list[Endpoint]:
    by_id, by_path = _v4l_maps()
    found: list[Endpoint] = []
    for node in sorted(glob.glob("/dev/video*")):
        base = os.path.basename(node)
        if not base.startswith("video"):
            continue
        try:
            index = int(base.replace("video", ""))
        except ValueError:
            continue
        sysname = _read(f"/sys/class/video4linux/{base}/name")
        parent = ""
        try:
            parent = os.path.realpath(f"/sys/class/video4linux/{base}/device")
        except OSError:
            parent = ""
        is_meta = "meta" in sysname.lower() or "touch" in sysname.lower()
        queried, card, bus = _query_capture(node)
        if is_meta:
            is_cap = False
        elif queried is None:
            is_cap = True
        else:
            is_cap = queried
        real = os.path.realpath(node)
        found.append(
            Endpoint(
                index=index,
                path=node,
                name=card or sysname or base,
                bus_info=bus,
                parent=parent or f"idx:{index}",
                by_id=by_id.get(real, ""),
                by_path=by_path.get(real, ""),
                is_capture=is_cap,
                is_metadata=is_meta,
            )
        )
    return found


def group_physical(endpoints: Iterable[Endpoint]) -> list[PhysicalDevice]:
    groups: dict[str, list[Endpoint]] = {}
    for ep in endpoints:
        key = ep.parent or ep.by_path or f"loose:{ep.index}"
        groups.setdefault(key, []).append(ep)
    devices: list[PhysicalDevice] = []
    used_ids: dict[str, int] = {}
    for parent, eps in groups.items():
        capture = [e for e in eps if e.is_capture and not e.is_metadata]
        if not capture:
            continue
        capture.sort(key=lambda e: e.index)
        primary = capture[0]
        stable, open_path, unique = _identity(primary)
        used_ids[stable] = used_ids.get(stable, 0) + 1
        name = primary.name or f"카메라 {primary.index}"
        note = ""
        hidden = len(eps) - 1
        if hidden > 0:
            note = f"같은 장치의 다른 노드 {hidden}개는 목록에서 묶었습니다."
        devices.append(
            PhysicalDevice(
                stable_id=stable,
                display_name=name,
                index=primary.index,
                open_path=open_path,
                kind=KIND_LOCAL,
                bus_info=primary.bus_info,
                unique=unique,
                connected=os.path.exists(open_path) or os.path.exists(primary.path),
                endpoint_count=len(eps),
                extra_note=note,
                aliases=[e.path for e in capture],
            )
        )
    for dev in devices:
        if used_ids.get(dev.stable_id, 0) > 1:
            dev.unique = False
            dev.extra_note = (dev.extra_note + " " if dev.extra_note else "") + (
                "식별자가 겹칩니다. 장치 경로를 확인하고 직접 선택하세요."
            )
    devices.sort(key=lambda d: d.index)
    return devices


def list_local_devices() -> list[PhysicalDevice]:
    global _ENUM_CACHE
    now = time.monotonic()
    cached_at, cached = _ENUM_CACHE
    if cached and now - cached_at < _ENUM_TTL:
        return list(cached)
    with _ENUM_LOCK:
        now = time.monotonic()
        cached_at, cached = _ENUM_CACHE
        if cached and now - cached_at < _ENUM_TTL:
            return list(cached)
        if os.path.isdir("/sys/class/video4linux") or glob.glob("/dev/video*"):
            try:
                devices = group_physical(list_linux_endpoints())
            except Exception:
                log.exception("v4l enumerate failed")
                devices = _scan_indexes()
        else:
            devices = _scan_indexes()
        _ENUM_CACHE = (time.monotonic(), devices)
        return list(devices)


def _scan_indexes() -> list[PhysicalDevice]:
    """V4L 정보가 없을 때의 불안정한 인덱스 스캔. 열어서 확인하므로 호출 스레드에서만 사용."""
    import cv2

    out: list[PhysicalDevice] = []
    for idx in range(0, 6):
        cap = cv2.VideoCapture(idx)
        try:
            if not cap.isOpened():
                continue
            out.append(
                PhysicalDevice(
                    stable_id=f"unstable:index:{idx}",
                    display_name=f"카메라 인덱스 {idx}",
                    index=idx,
                    open_path=str(idx),
                    unique=False,
                    extra_note="안정적인 장치 ID를 얻지 못했습니다. 재시작 후 다른 카메라에 연결될 수 있어 다시 선택이 필요합니다.",
                )
            )
        finally:
            cap.release()
    return out


def list_demo_devices() -> list[PhysicalDevice]:
    return list(DEMO_DEVICES)


def find_device(devices: list[PhysicalDevice], stable_id: str) -> Optional[PhysicalDevice]:
    hits = [d for d in devices if _id_match(d.stable_id, stable_id)]
    if len(hits) == 1:
        return hits[0]
    return None


def _identity(ep: Endpoint) -> tuple[str, str, bool]:
    """(stable_id, open_path, unique).

    안정 ID(by-id)와 실제 캡처 입력(/dev/videoN)을 분리한다.
    OpenCV에는 심볼릭 링크가 아니라 캡처 노드를 넘긴다.
    """
    if ep.by_id:
        sid = ep.by_id if ep.by_id.startswith("/") else f"/dev/v4l/by-id/{ep.by_id}"
        return sid, ep.path, True
    if ep.by_path:
        sid = ep.by_path if ep.by_path.startswith("/") else f"/dev/v4l/by-path/{ep.by_path}"
        return sid, ep.path, True
    return f"unstable:index:{ep.index}", ep.path, False


def _id_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if a.startswith("/dev/") and b.startswith("/dev/"):
        return os.path.basename(a) == os.path.basename(b)
    return False


def _capture_node(path: str) -> str:
    """심볼릭 링크를 실제 /dev/videoN 캡처 노드로 푼다. 목록 순번을 인덱스로 쓰지 않는다."""
    if not path:
        return ""
    candidate = path
    if os.path.exists(path):
        candidate = os.path.realpath(path)
    base = os.path.basename(candidate)
    if base.startswith("video") and candidate.startswith("/dev/"):
        return candidate
    return ""


def describe_device_access(path: str) -> str:
    """열기 전 권한·점유를 errno로 구분한다. 빈 문자열이면 파일은 열 수 있다."""
    import errno

    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        os.close(fd)
        return ""
    except FileNotFoundError:
        return f"장치 파일이 없습니다 ({path})"
    except PermissionError:
        return "카메라에 접근할 권한이 없습니다. 사용자를 video 그룹에 넣고 다시 로그인하세요."
    except OSError as exc:
        if exc.errno == errno.EBUSY:
            return "다른 프로그램이 이 카메라를 사용 중입니다. 미리보기나 다른 앱을 종료하세요."
        return f"장치를 열 수 없습니다: {exc.strerror}"


def capture_targets(camera) -> tuple[list[str], str, str]:
    """안정 ID로 현재 캡처 노드 목록을 만든다. 첫 항목이 주 입력."""
    source, state, detail = resolve_open_source(camera)
    paths: list[str] = []
    if isinstance(source, str) and source:
        node = _capture_node(source) or source
        paths.append(node)
    try:
        devices = list_local_devices()
    except Exception:
        devices = []
    hit = find_device(devices, camera.device_id or "")
    if hit:
        for p in [hit.open_path, *hit.aliases]:
            node = _capture_node(p) or p
            if node and node not in paths:
                paths.append(node)
    return paths, state, detail


def resolve_open_source(camera) -> tuple[object, str, str]:
    """저장된 할당으로 열 소스. 인덱스로 추측해 잘못된 카메라를 열지 않는다.

    Returns:
        (source, match_state, detail). source=None 이면 열지 말 것.
        로컬 장치는 /dev/videoN 캡처 노드를 반환한다 (by-id 링크가 아님).
    """
    from dolbom.models import (
        MATCH_AMBIGUOUS,
        MATCH_MISSING,
        MATCH_OK,
        MATCH_UNSET,
        MATCH_UNSTABLE,
        SOURCE_DEMO,
        SOURCE_RTSP,
    )

    if camera.source_kind == SOURCE_RTSP or str(camera.device_id or "").startswith("rtsp:"):
        src = camera.source_value or camera.device_path
        if src:
            return src, MATCH_OK, ""
        return None, MATCH_UNSET, "네트워크 카메라 주소가 없습니다."
    if camera.source_kind == SOURCE_DEMO or str(camera.device_id or "").startswith("demo:"):
        return None, MATCH_OK, "demo"
    device_id = camera.device_id or ""
    path = camera.device_path or ""
    if device_id.startswith("unstable:"):
        return None, MATCH_UNSTABLE, "안정적인 장치 ID가 없어 다시 선택해야 합니다."
    node = _capture_node(path)
    try:
        devices = list_local_devices()
    except Exception:
        devices = []
    hits = [d for d in devices if _id_match(d.stable_id, device_id)]
    if len(hits) == 1 and hits[0].unique:
        return hits[0].open_path, MATCH_OK, ""
    if len(hits) > 1:
        return None, MATCH_AMBIGUOUS, "같은 식별자의 장치가 여러 대입니다. 다시 선택하세요."
    if node and os.path.exists(node):
        return node, MATCH_OK, ""
    node = _capture_node(device_id)
    if node and os.path.exists(node):
        return node, MATCH_OK, ""
    if device_id:
        return None, MATCH_MISSING, "저장된 장치를 찾지 못했습니다. 다시 선택하세요."
    return None, MATCH_UNSET, "장치가 아직 지정되지 않았습니다."
