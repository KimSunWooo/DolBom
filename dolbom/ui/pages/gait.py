from __future__ import annotations

import time

from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.services import AppServices
from dolbom.models import (
    CAM_DISCONNECTED,
    CAM_RECONNECTING,
    CAM_STATUS_LABELS,
    MODE_EXERCISE,
    MODE_GAIT,
    MODE_LABELS,
)
from dolbom.ui.dialogs import confirm
from dolbom.ui.widgets import StatusChip, VideoSurface, make_button


class GaitPage(QWidget):
    def __init__(self, services: AppServices):
        super().__init__()
        self.services = services
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        head = QHBoxLayout()
        title = QLabel("보행")
        title.setObjectName("sectionTitle")
        self.patient = QComboBox()
        self.camera = QComboBox()
        self.session_chip = StatusChip("세션 없음", "muted")
        self.elapsed = QLabel("경과 00:00")
        head.addWidget(title)
        head.addSpacing(12)
        head.addWidget(QLabel("환자"))
        head.addWidget(self.patient, 1)
        head.addWidget(QLabel("촬영 카메라"))
        head.addWidget(self.camera, 1)
        head.addWidget(self.session_chip)
        head.addWidget(self.elapsed)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        self.view = VideoSurface("카메라를 선택하면 넓은 미리보기가 표시됩니다")
        self.view.setToolTip("보행 미리보기. 전송 시작 전에 구도를 확인하세요.")
        try:
            self.view.clicked.disconnect()
        except TypeError:
            pass
        chips = QHBoxLayout()
        self.live_chip = StatusChip("미리보기 대기", "muted")
        self.send_chip = StatusChip("전송 안 함", "muted")
        self.msg_chip = StatusChip("서버 메시지 없음", "muted")
        chips.addWidget(self.live_chip)
        chips.addWidget(self.send_chip)
        chips.addWidget(self.msg_chip)
        chips.addStretch()
        row = QHBoxLayout()
        self.start_btn = make_button("전송 시작", "primary", "보행 영상을 서버로 보냅니다.")
        self.end_btn = make_button("세션 종료", "danger", "보행 세션과 전송을 끝냅니다.")
        self.start_btn.clicked.connect(self._start)
        self.end_btn.clicked.connect(self._end)
        row.addWidget(self.start_btn)
        row.addWidget(self.end_btn)
        row.addStretch()
        note = QLabel(
            "보행 지표·AI 분석은 이 프로그램에서 계산하지 않습니다. "
            "운동과 같은 카메라를 쓸 수 있으나 동시에 두 세션을 만들 수는 없습니다."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        cl.addWidget(self.view, 1)
        cl.addLayout(chips)
        cl.addLayout(row)
        cl.addWidget(note)

        root.addLayout(head)
        root.addWidget(card, 1)

        services.cameras.frame_ready.connect(self._frame)
        services.sessions.session_changed.connect(self._refresh)
        services.messages.changed.connect(self._on_msg)
        self.reload_patients()
        self.reload_cameras()
        self._refresh()

    def reload_patients(self) -> None:
        cur = self.patient.currentData()
        self.patient.blockSignals(True)
        self.patient.clear()
        self.patient.addItem("선택 안 함", None)
        for p in self.services.store.list_patients():
            label = f"{p.display_name}" + (f" · {p.room}" if p.room else "")
            self.patient.addItem(label, p.id)
        if cur is not None:
            idx = self.patient.findData(cur)
            if idx >= 0:
                self.patient.setCurrentIndex(idx)
        self.patient.blockSignals(False)

    def reload_cameras(self) -> None:
        cur = self.camera.currentData()
        self.camera.blockSignals(True)
        self.camera.clear()
        enabled = [c for c in self.services.store.list_cameras() if c.enabled]
        if not enabled:
            self.camera.addItem("등록된 카메라 없음", None)
        for c in enabled:
            self.camera.addItem(f"{c.name} · {c.location}", c.id)
        if cur is not None:
            idx = self.camera.findData(cur)
            if idx >= 0:
                self.camera.setCurrentIndex(idx)
        self.camera.blockSignals(False)

    def _start(self) -> None:
        cam_id = self.camera.currentData()
        if not cam_id:
            QMessageBox.information(self, "카메라 필요", "촬영할 카메라를 선택하세요.")
            return
        live = self.services.sessions.clinical()
        if live:
            other = MODE_LABELS.get(live.mode, live.mode)
            if not confirm(
                self,
                "세션 전환",
                f"진행 중인 {other} 세션을 종료한 뒤 보행 전송을 시작할까요?\n메뉴만 바꿔서는 기존 세션이 끝나지 않습니다.",
            ):
                return
            self.services.sessions.end_clinical("switched")
        ok, reason, _ = self.services.sessions.start_clinical(
            mode=MODE_GAIT,
            camera_id=cam_id,
            patient_id=self.patient.currentData(),
            playlist_item_id=None,
            title=None,
            topic=None,
        )
        if not ok:
            QMessageBox.information(self, "전송을 시작하지 못했습니다", reason)

    def _end(self) -> None:
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_GAIT:
            self.services.sessions.end_clinical("ended")

    def _frame(self, frame) -> None:
        cam_id = self.camera.currentData()
        if cam_id and frame.camera_id == cam_id:
            self.view.set_frame(frame.bgr)

    def _refresh(self) -> None:
        live = self.services.sessions.clinical()
        sending = bool(live and live.mode == MODE_GAIT)
        cam_id = self.camera.currentData()
        status, detail, seen = self.services.cameras.last_status(cam_id) if cam_id else ("", "", 0)
        if sending:
            self.session_chip.set_tone("ok", "보행 세션 전송 중")
            self.live_chip.set_tone("ok", "서버 전송 중")
            self.send_chip.set_tone("ok", "보행 영상 전송 중")
        else:
            bg = "다른 세션 진행 중" if live else "세션 없음 · 미리보기"
            self.session_chip.set_tone("warn" if live else "muted", bg)
            self.live_chip.set_tone("teal", "미리보기 중")
            self.send_chip.set_tone("muted", "전송 안 함")
        if status in (CAM_DISCONNECTED, CAM_RECONNECTING):
            self.live_chip.set_tone("urgent", CAM_STATUS_LABELS.get(status, status))
            self.view.set_overlay("보행 카메라", CAM_STATUS_LABELS.get(status, status), True, seen)
        else:
            self.view.set_overlay(
                "보행 카메라",
                "서버 전송 중" if sending else "미리보기 중 · 아직 서버로 보내지 않음",
                False,
            )
        self.start_btn.setEnabled(not sending)
        self.end_btn.setEnabled(sending)

    def _on_msg(self) -> None:
        latest = self.services.messages.latest()
        if not latest:
            self.msg_chip.set_tone("muted", "서버 메시지 없음")
            return
        text = latest.content[:40]
        if latest.is_test:
            self.msg_chip.set_tone("teal", f"시험 · {text}")
        elif latest.severity == "urgent":
            self.msg_chip.set_tone("urgent", text)
        else:
            self.msg_chip.set_tone("warn", text)

    def tick(self) -> None:
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_GAIT:
            sec = int(time.monotonic() - live.started_mono)
            self.elapsed.setText(f"경과 {sec // 60:02d}:{sec % 60:02d}")
        else:
            self.elapsed.setText("경과 00:00")
        self._refresh()
