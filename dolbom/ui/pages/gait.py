from __future__ import annotations

import time

from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.assignment import clinical_camera
from dolbom.core.services import AppServices
from dolbom.models import (
    CAM_DISCONNECTED,
    CAM_RECONNECTING,
    CAM_STATUS_LABELS,
    MODE_GAIT,
    MODE_LABELS,
)
from dolbom.ui.device_picker import DevicePickerDialog
from dolbom.ui.dialogs import confirm
from dolbom.ui.patient_panel import PatientPanel
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
        self.session_chip = StatusChip("세션 없음", "muted")
        self.elapsed = QLabel("경과 00:00")
        self.cam_name = QLabel("운동·보행 카메라")
        self.pick_cam = make_button("카메라 선택", tooltip="운동과 보행이 같이 쓰는 공용 카메라입니다.")
        self.retry_cam = make_button("재연결")
        self.pick_cam.clicked.connect(self._pick_camera)
        self.retry_cam.clicked.connect(self._retry_camera)
        head.addWidget(title)
        head.addSpacing(12)
        head.addWidget(self.cam_name, 1)
        head.addWidget(self.pick_cam)
        head.addWidget(self.retry_cam)
        head.addWidget(self.session_chip)
        head.addWidget(self.elapsed)

        self.patient_panel = PatientPanel(
            services.patients, session_patient_id_fn=self._session_patient_id
        )
        self.patient_panel.selection_changed.connect(self._on_patient)
        self.patient_panel.change_during_session.connect(self._patient_switch)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        self.live_who = QLabel("선택된 환자가 없습니다.")
        self.live_who.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.view = VideoSurface("공용 카메라를 선택하면 넓은 미리보기가 표시됩니다")
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
            "보행 지표는 계산하지 않습니다. 운동과 같은 공용 카메라를 쓰며 동시에 두 세션을 만들 수 없습니다."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        cl.addWidget(self.live_who)
        cl.addWidget(self.view, 1)
        cl.addLayout(chips)
        cl.addLayout(row)
        cl.addWidget(note)

        body = QHBoxLayout()
        body.addWidget(self.patient_panel, 0)
        body.addWidget(card, 1)

        root.addLayout(head)
        root.addLayout(body, 1)

        services.cameras.frame_ready.connect(self._frame)
        services.sessions.session_changed.connect(self._refresh)
        services.messages.changed.connect(self._on_msg)
        services.cameras_changed.connect(self.reload_clinical_camera)
        self.reload_clinical_camera()
        self._refresh()

    def _session_patient_id(self) -> str | None:
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_GAIT:
            return live.patient_id
        return None

    def reload_patients(self) -> None:
        self.patient_panel.reload()

    def reload_cameras(self) -> None:
        self.reload_clinical_camera()

    def reload_clinical_camera(self) -> None:
        cam = clinical_camera(self.services.store.list_cameras())
        if cam is None:
            self.cam_name.setText("운동·보행 카메라 슬롯 없음")
            return
        src = cam.display_source() if cam.device_id or cam.source_kind == "rtsp" else "장치 미지정"
        self.cam_name.setText(f"{cam.name}  ·  {src}")

    def _clinical_id(self) -> str | None:
        cam = clinical_camera(self.services.store.list_cameras())
        return cam.id if cam else None

    def _pick_camera(self) -> None:
        cam = clinical_camera(self.services.store.list_cameras())
        if not cam:
            return
        DevicePickerDialog(self.services, cam, self).exec()
        self.reload_clinical_camera()

    def _retry_camera(self) -> None:
        cam_id = self._clinical_id()
        if cam_id:
            self.services.cameras.reopen(cam_id)

    def _on_patient(self, patient) -> None:
        if patient:
            self.live_who.setText(f"선택 환자  {patient.display_name}  ·  {patient.id}")
        else:
            self.live_who.setText("선택된 환자가 없습니다.")

    def _patient_switch(self, patient) -> None:
        if not confirm(
            self,
            "세션 대상 변경",
            f"진행 중인 세션 대상은 그대로입니다. ‘{patient.display_name}’으로 바꾸려면 세션을 종료해야 합니다.\n종료하고 대상을 바꿀까요?",
        ):
            live = self.services.sessions.clinical()
            if live and live.patient_id:
                self.patient_panel.select_id(live.patient_id)
            return
        self.services.sessions.end_clinical("patient_changed")
        self.patient_panel.set_frozen(None)
        self.patient_panel.apply_patient(patient)
        self._on_patient(patient)

    def _start(self) -> None:
        cam_id = self._clinical_id()
        if not cam_id:
            QMessageBox.information(self, "카메라 필요", "운동·보행 공용 카메라를 먼저 선택하세요.")
            return
        patient = self.patient_panel.selected()
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
            patient_id=patient.id if patient else None,
            playlist_item_id=None,
            title=None,
            topic=None,
        )
        if not ok:
            QMessageBox.information(self, "전송을 시작하지 못했습니다", reason)
            return
        self.patient_panel.set_frozen(patient)

    def _end(self) -> None:
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_GAIT:
            self.services.sessions.end_clinical("ended")
            self.patient_panel.set_frozen(None)

    def _frame(self, frame) -> None:
        cam_id = self._clinical_id()
        if cam_id and frame.camera_id == cam_id:
            self.view.set_frame(frame.bgr)

    def _refresh(self) -> None:
        live = self.services.sessions.clinical()
        sending = bool(live and live.mode == MODE_GAIT)
        cam_id = self._clinical_id()
        status, detail, seen = self.services.cameras.last_status(cam_id) if cam_id else ("", "", 0)
        if sending:
            self.session_chip.set_tone("ok", "보행 세션 전송 중")
            self.live_chip.set_tone("ok", "서버 전송 중")
            self.send_chip.set_tone("ok", "보행 영상 전송 중")
            if live.patient_id:
                try:
                    p = self.services.patients.get(live.patient_id)
                    self.live_who.setText(
                        f"세션 대상  {p.display_name}  ·  {p.id}" if p else f"세션 대상  {live.patient_id}"
                    )
                except Exception:
                    self.live_who.setText(f"세션 대상  {live.patient_id}")
        else:
            bg = "다른 세션 진행 중" if live else "세션 없음 · 미리보기"
            self.session_chip.set_tone("warn" if live else "muted", bg)
            self.live_chip.set_tone("teal", "미리보기 중")
            self.send_chip.set_tone("muted", "전송 안 함")
        if status in (CAM_DISCONNECTED, CAM_RECONNECTING):
            self.live_chip.set_tone("urgent", CAM_STATUS_LABELS.get(status, status))
            self.view.clear_frame()
            self.view.set_overlay(
                "보행 카메라",
                detail or "연결 끊김 · 재연결 또는 장치를 다시 선택하세요",
                True,
                seen,
            )
            self.retry_cam.setEnabled(True)
        else:
            self.retry_cam.setEnabled(False)
            self.view.set_overlay(
                "보행 카메라",
                "서버 전송 중" if sending else "미리보기 중 · 아직 서버로 보내지 않음",
                False,
            )
        self.start_btn.setEnabled(not sending)
        self.end_btn.setEnabled(sending)
        self.reload_clinical_camera()

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
