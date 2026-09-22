"""표준 운동 샘플 영상 생성. 앱 데이터 폴더에만 만들며 원본 사용자 파일은 건드리지 않는다."""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication

from dolbom.models import PLAYLIST_LOCAL, PlaylistItem
from dolbom.paths import samples_dir


SAMPLES = [
    ("어깨를 천천히 올리기", "어깨운동", "앉은 자세에서 어깨를 귀 쪽으로 올렸다가 내립니다."),
    ("무릎 펴고 굽히기", "다리운동", "의자에 앉아 한쪽 무릎을 천천히 폈다가 굽힙니다."),
    ("고개 좌우로 돌리기", "목운동", "시선을 정면에 두고 고개를 천천히 좌우로 돌립니다."),
]


def _qimage_to_bgr(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h = converted.width(), converted.height()
    bpl = converted.bytesPerLine()
    ptr = converted.bits()
    ptr.setsize(h * bpl)
    raw = np.frombuffer(ptr, np.uint8).reshape((h, bpl))
    arr = raw[:, : w * 3].reshape((h, w, 3)).copy()
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _draw_frame(title: str, topic: str, n: int, total: int) -> np.ndarray:
    image = QImage(640, 360, QImage.Format.Format_RGB888)
    image.fill(QColor("#3C7380"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#FFFFFF")))
    font = QApplication.font()
    font.setPointSize(20)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRect(24, 40, 592, 50), Qt.AlignmentFlag.AlignLeft, title)
    font.setPointSize(13)
    font.setBold(False)
    painter.setFont(font)
    painter.drawText(QRect(24, 96, 592, 32), Qt.AlignmentFlag.AlignLeft, f"토픽  {topic}")
    painter.drawText(
        QRect(24, 300, 592, 32),
        Qt.AlignmentFlag.AlignLeft,
        f"표준 운동 안내 영상  {n + 1}/{total}",
    )
    # moving cue circle — not a skeleton / score
    t = n / max(1, total - 1)
    x = int(80 + t * 480)
    painter.setBrush(QColor("#F4F1EA"))
    painter.drawEllipse(x, 180, 36, 36)
    painter.end()
    return _qimage_to_bgr(image)


def ensure_samples() -> list[PlaylistItem]:
    folder = samples_dir()
    items: list[PlaylistItem] = []
    total = 48
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    for i, (title, topic, desc) in enumerate(SAMPLES):
        path = folder / f"sample_{i}.avi"
        if not path.exists():
            writer = cv2.VideoWriter(str(path), fourcc, 12.0, (640, 360))
            if writer.isOpened():
                for n in range(total):
                    writer.write(_draw_frame(title, topic, n, total))
                writer.release()
        items.append(
            PlaylistItem(
                id=str(uuid.uuid4()),
                title=title,
                topic=topic,
                source_kind=PLAYLIST_LOCAL,
                path_or_url=str(path),
                description=desc,
                sort_order=i,
            )
        )
    return items
