"""병실 CCTV 낙상·특이사항을 메인 화면에 바로 보여 주는 칸. 시스템 로그와 분리한다."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from dolbom.models import AppMessage, SEVERITY_LABELS
from dolbom.ui.widgets import StatusChip, make_button


class CctvAlertRail(QFrame):
    open_cctv = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("cctvAlertRail")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)
        self.kind = StatusChip("병실 CCTV 알람", "muted")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = QLabel("낙상·특이사항 없음")
        self.title.setObjectName("sectionTitle")
        self.detail = QLabel("병실 CCTV에서 낙상 알람이나 특이사항이 오면 추가 조작 없이 여기에 표시됩니다.")
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.detail)
        self.go_btn = make_button("병실 CCTV로", "primary", "알람이 난 병실 CCTV 화면으로 바로 이동합니다.")
        self.go_btn.clicked.connect(self.open_cctv.emit)
        layout.addWidget(self.kind)
        layout.addLayout(texts, 1)
        layout.addWidget(self.go_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.refresh([])

    def refresh(self, alerts: list[AppMessage]) -> None:
        if not alerts:
            self.setProperty("alert", "false")
            self.kind.set_tone("muted", "병실 CCTV 알람")
            self.title.setText("낙상·특이사항 없음")
            self.detail.setText("병실 CCTV에서 낙상 알람이나 특이사항이 오면 추가 조작 없이 여기에 표시됩니다.")
            self._repolish()
            return
        live = [m for m in alerts if not m.acknowledged]
        show = live or alerts[:1]
        first = show[0]
        extra = len(live) - 1 if live else 0
        label = SEVERITY_LABELS.get(first.severity, "알람")
        if first.is_test:
            label = f"시험 · {label}"
        tone = "urgent" if first.severity == "urgent" and not first.is_test else "warn"
        self.setProperty("alert", "true" if alerts else "false")
        self.kind.set_tone(tone, f"병실 CCTV 알람  {len(live) if live else 1}건")
        loc = f" · {first.location}" if first.location else ""
        more = f"  외 {extra}건" if extra > 0 else ""
        self.title.setText(f"{label}{loc}{more}")
        when = first.occurred_at.replace("T", " ")
        self.detail.setText(f"{when}  {first.content}")
        self._repolish()

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
