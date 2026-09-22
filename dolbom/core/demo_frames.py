"""합성 카메라 프레임. 데모 모드 전용이며 실제 카메라와 구분한다."""

from __future__ import annotations

import time

import cv2
import numpy as np


PALETTES = {
    "warm": ((62, 92, 118), (90, 150, 170)),
    "cool": ((118, 92, 62), (160, 140, 90)),
    "green": ((60, 100, 70), (90, 150, 110)),
    "purple": ((90, 60, 90), (140, 100, 140)),
}


def make_demo_frame(
    *,
    camera_name: str,
    location: str,
    source_key: str,
    frame_no: int,
    width: int = 640,
    height: int = 360,
) -> np.ndarray:
    bg, accent = PALETTES.get(source_key, PALETTES["warm"])
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = bg
    t = time.time()
    x = int((np.sin(t) * 0.4 + 0.5) * (width - 80))
    y = int((np.cos(t * 0.7) * 0.3 + 0.5) * (height - 80))
    cv2.rectangle(img, (x, y), (x + 70, y + 70), accent, -1)
    cv2.rectangle(img, (0, 0), (width - 1, height - 1), (200, 210, 220), 2)
    stamp = time.strftime("%H:%M:%S")
    lines = [
        "DEMO — not a live camera",
        camera_name[:32],
        location[:32],
        f"{stamp}  f{frame_no}",
    ]
    y0 = 28
    for line in lines:
        cv2.putText(
            img,
            line,
            (16, y0),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (240, 244, 246),
            1,
            cv2.LINE_AA,
        )
        y0 += 26
    return img
