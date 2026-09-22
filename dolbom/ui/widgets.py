from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dolbom.models import (
    CAM_STATUS_LABELS,
    MSG_CAMERA_ERROR,
    MSG_INFO,
    MSG_SERVER_ERROR,
    MSG_URGENT,
    SEVERITY_LABELS,
    AppMessage,
)
from dolbom.theme import INK, INK_MUTED, LINE, OK, TEAL, TEAL_DEEP, URGENT, VIDEO_BG, WARN, set_kind

log = logging.getLogger("dolbom.ui.video")


def bgr_to_qimage(bgr: np.ndarray) -> QImage:
    if bgr is None or getattr(bgr, "size", 0) == 0:
        return QImage()
    frame = np.ascontiguousarray(bgr)
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.ndim != 3:
        return QImage()
    channels = frame.shape[2]
    if channels == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    elif channels != 3:
        return QImage()
    bgra = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA))
    h, w = bgra.shape[:2]
    qimg = QImage(bgra.data, w, h, int(bgra.strides[0]), QImage.Format.Format_RGB32)
    return qimg.copy()


def make_button(text: str, kind: str | None = None, tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    if kind:
        set_kind(btn, kind)
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class StatusChip(QLabel):
    def __init__(self, text: str = "", tone: str = "muted"):
        super().__init__(text)
        self.set_tone(tone, text)

    def set_tone(self, tone: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        colors = {
            "ok": (OK, "#E7F0EA"),
            "teal": (TEAL_DEEP, "#D7E6E9"),
            "warn": (WARN, "#F6EBD9"),
            "urgent": (URGENT, "#F8E5E2"),
            "muted": (INK_MUTED, "#EEEAE3"),
        }
        fg, bg = colors.get(tone, colors["muted"])
        self.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; border-radius: 12px; "
            f"padding: 4px 10px; font-weight: 600; font-size: 12px; }}"
        )


class EmptyState(QFrame):
    def __init__(self, title: str, body: str, action: QPushButton | None = None):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        t = QLabel(title)
        t.setObjectName("sectionTitle")
        t.setWordWrap(True)
        b = QLabel(body)
        b.setObjectName("muted")
        b.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(b)
        if action:
            layout.addWidget(action, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()


class VideoSurface(QWidget):
    clicked = pyqtSignal()

    def __init__(self, placeholder: str = "영상 없음"):
        super().__init__()
        self._image: Optional[QImage] = None
        self._placeholder = placeholder
        self._overlay_title = ""
        self._overlay_status = ""
        self._disconnected = False
        self._last_seen = 0.0
        self._alert = False
        self._logged_first = False
        self.setMinimumSize(240, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("클릭하면 확대 보기")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def set_frame(self, bgr: np.ndarray) -> None:
        image = bgr_to_qimage(bgr)
        if image.isNull():
            if not self._logged_first:
                log.info("ui frame convert failed widget=%s", self._overlay_title or self._placeholder)
            return
        if not self._logged_first:
            self._logged_first = True
            log.info(
                "ui first frame widget=%s size=%sx%s",
                self._overlay_title or self._placeholder,
                image.width(),
                image.height(),
            )
        self._image = image
        self.update()

    def set_qimage(self, image: QImage) -> None:
        self._image = image
        self.update()

    def clear_frame(self) -> None:
        self._image = None
        self.update()

    def set_overlay(
        self,
        title: str = "",
        status: str = "",
        disconnected: bool = False,
        last_seen: float = 0.0,
        alert: bool = False,
    ) -> None:
        self._overlay_title = title
        self._overlay_status = status
        self._disconnected = disconnected
        self._last_seen = last_seen
        self._alert = alert
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(VIDEO_BG))
        if self._image and not self._image.isNull():
            pix = QPixmap.fromImage(self._image)
            scaled = pix.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            if self._disconnected:
                painter.fillRect(QRect(x, y, scaled.width(), scaled.height()), QColor(20, 22, 24, 150))
        else:
            painter.setPen(QColor("#C5CCD3"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder)

        if self._alert:
            painter.setPen(QPen(QColor(URGENT), 4))
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))

        if self._overlay_title or self._overlay_status or self._disconnected:
            bar = QRect(0, self.height() - 46, self.width(), 46)
            painter.fillRect(bar, QColor(18, 20, 22, 190))
            painter.setPen(QColor("#F4F1EA"))
            font = painter.font()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(bar.adjusted(10, 4, -10, -18), Qt.AlignmentFlag.AlignLeft, self._overlay_title)
            font.setBold(False)
            painter.setFont(font)
            status = self._overlay_status
            if self._disconnected:
                seen = time.strftime("%H:%M:%S", time.localtime(self._last_seen)) if self._last_seen else "—"
                status = f"연결 끊김 · 마지막 수신 {seen}  · 실시간 아님"
            painter.drawText(bar.adjusted(10, 22, -10, -4), Qt.AlignmentFlag.AlignLeft, status)


class MessageBar(QFrame):
    open_all = pyqtSignal()
    jump = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("messageBar")
        self.setFixedHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        self.count = StatusChip("미확인 0", "muted")
        self.summary = QLabel("아직 받은 메시지가 없습니다.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        self.kind = StatusChip("안내", "muted")
        self.open_btn = make_button("전체 메시지", tooltip="메시지 이력 패널을 엽니다. Ctrl+M")
        self.open_btn.clicked.connect(self.open_all.emit)
        layout.addWidget(self.count)
        layout.addWidget(self.kind)
        layout.addWidget(self.summary, 1)
        layout.addWidget(self.open_btn)

    def refresh(self, unread: int, latest: Optional[AppMessage]) -> None:
        self.count.set_tone("urgent" if unread else "muted", f"미확인 {unread}")
        if latest is None:
            self.kind.set_tone("muted", "안내")
            self.summary.setText("아직 받은 메시지가 없습니다.")
            return
        tone = {
            MSG_URGENT: "urgent",
            MSG_CAMERA_ERROR: "warn",
            MSG_SERVER_ERROR: "warn",
            MSG_INFO: "teal",
        }.get(latest.severity, "muted")
        label = SEVERITY_LABELS.get(latest.severity, "안내")
        if latest.is_test:
            label = f"시험 · {label}"
        self.kind.set_tone(tone, label)
        prefix = "[시험] " if latest.is_test and not latest.content.startswith("[시험]") else ""
        self.summary.setText(f"{prefix}{latest.content}")
