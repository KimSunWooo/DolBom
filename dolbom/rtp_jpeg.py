"""
JPEG over RTP (RFC 2435 단순화) + UDP 전송.

근거:
- 원본 프레임을 단일 UDP 패킷으로 보내지 않는다 (MTU 초과 방지).
- GStreamer 파이프라인 대신 표준 RTP 헤더 + JPEG 페이로드만 구현해
  Windows/macOS/Linux에서 의존성이 OpenCV+소켓으로 유지된다.
- 수신 측은 시퀀스/마커 비트로 프레임을 재조립하면 된다.

이 구현은 메인 서버 프로덕션 코덱 합의가 아니며, 시험 수신기와
추후 서버 연동을 위한 transport 계층이다.
"""

from __future__ import annotations

import struct
import time
from typing import Iterable

RTP_VERSION = 2
RTP_PAYLOAD_JPEG = 26
MAX_PAYLOAD = 1200  # RTP 헤더·JPEG 헤더를 제외한 조각 크기. 이더넷 MTU 여유.


def rtp_timestamp(clock_rate: int = 90000) -> int:
    return int(time.monotonic() * clock_rate) & 0xFFFFFFFF


def pack_rtp_header(
    *,
    payload_type: int,
    seq: int,
    timestamp: int,
    ssrc: int,
    marker: bool,
) -> bytes:
    b0 = (RTP_VERSION << 6) & 0xFF
    b1 = (payload_type & 0x7F) | (0x80 if marker else 0x00)
    return struct.pack("!BBHII", b0, b1, seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc & 0xFFFFFFFF)


def pack_jpeg_header(*, fragment_offset: int, type_specific: int = 0, jpeg_type: int = 1, q: int = 255, width: int, height: int) -> bytes:
    """RFC 2435 8바이트 JPEG 헤더. width/height 는 8픽셀 단위."""
    w8 = max(1, min(255, (width + 7) // 8))
    h8 = max(1, min(255, (height + 7) // 8))
    return struct.pack(
        "!BBBBBBBB",
        type_specific & 0xFF,
        (fragment_offset >> 16) & 0xFF,
        (fragment_offset >> 8) & 0xFF,
        fragment_offset & 0xFF,
        jpeg_type & 0xFF,
        q & 0xFF,
        w8,
        h8,
    )


def packetize_jpeg(
    jpeg: bytes,
    *,
    seq_start: int,
    timestamp: int,
    ssrc: int,
    width: int,
    height: int,
) -> tuple[list[bytes], int]:
    packets: list[bytes] = []
    offset = 0
    seq = seq_start
    total = len(jpeg)
    if total == 0:
        return [], seq
    while offset < total:
        chunk = jpeg[offset : offset + MAX_PAYLOAD]
        marker = offset + len(chunk) >= total
        header = pack_rtp_header(
            payload_type=RTP_PAYLOAD_JPEG,
            seq=seq,
            timestamp=timestamp,
            ssrc=ssrc,
            marker=marker,
        )
        jpeg_hdr = pack_jpeg_header(fragment_offset=offset, width=width, height=height)
        packets.append(header + jpeg_hdr + chunk)
        seq = (seq + 1) & 0xFFFF
        offset += len(chunk)
    return packets, seq


def parse_rtp(packet: bytes) -> dict:
    if len(packet) < 20:
        raise ValueError("packet too short")
    b0, b1, seq, ts, ssrc = struct.unpack("!BBHII", packet[:12])
    marker = bool(b1 & 0x80)
    pt = b1 & 0x7F
    off = (packet[13] << 16) | (packet[14] << 8) | packet[15]
    return {
        "seq": seq,
        "timestamp": ts,
        "ssrc": ssrc,
        "marker": marker,
        "payload_type": pt,
        "fragment_offset": off,
        "payload": packet[20:],
        "version": (b0 >> 6) & 0x03,
    }


def reassemble(packets: Iterable[bytes]) -> bytes:
    parts = [parse_rtp(p) for p in packets]
    parts.sort(key=lambda x: x["fragment_offset"])
    return b"".join(p["payload"] for p in parts)
