from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.assignment import clinical_camera
from dolbom.core.services import AppServices
from dolbom.media.player import StandardPlayer, classify_item, status_reason
from dolbom.models import (
    CAM_DISCONNECTED,
    CAM_RECONNECTING,
    CAM_STATUS_LABELS,
    MEDIA_MISSING_FILE,
    MEDIA_OK,
    MEDIA_WEBPAGE,
    MODE_EXERCISE,
    MODE_GAIT,
    MODE_LABELS,
    ROLE_CLINICAL,
    PlaylistItem,
)
from dolbom.ui.device_picker import DevicePickerDialog
from dolbom.ui.dialogs import PlaylistEditor, confirm
from dolbom.ui.patient_panel import PatientPanel
from dolbom.ui.widgets import StatusChip, VideoSurface, make_button


class ExercisePage(QWidget):
    def __init__(self, services: AppServices):
        super().__init__()
        self.services = services
        self.player = StandardPlayer()
        self._current: PlaylistItem | None = None
        self._external = ""
        self._seeking = False
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        head = QHBoxLayout()
        title = QLabel("운동")
        title.setObjectName("sectionTitle")
        self.session_chip = StatusChip("세션 없음", "muted")
        self.elapsed = QLabel("경과 00:00")
        self.cam_name = QLabel("운동·보행 카메라")
        self.pick_cam = make_button("카메라 선택", tooltip="운동과 보행이 같이 쓰는 공용 카메라를 지정합니다.")
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

        split = QHBoxLayout()
        left = QFrame()
        left.setObjectName("card")
        ll = QVBoxLayout(left)
        self.std_title = QLabel("표준 운동 영상")
        self.std_title.setObjectName("sectionTitle")
        self.std_meta = QLabel("재생목록에서 영상을 선택하세요.")
        self.std_meta.setObjectName("muted")
        self.std_meta.setWordWrap(True)
        self.std_view = VideoSurface("표준 영상이 여기에 표시됩니다")
        self.std_view.setToolTip("표준 운동 안내 영상")
        self.std_view.setCursor(Qt.CursorShape.ArrowCursor)
        try:
            self.std_view.clicked.disconnect()
        except TypeError:
            pass
        controls = QHBoxLayout()
        self.play_btn = make_button("재생", "primary", "표준 운동 영상을 재생합니다.")
        self.pause_btn = make_button("일시정지", tooltip="표준 영상만 일시정지합니다. 세션 전송은 멈추지 않습니다.")
        self.loop = QCheckBox("반복 재생")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.open_ext = make_button("브라우저에서 열기", tooltip="내부 재생이 불가능한 주소를 기본 브라우저로 엽니다.")
        self.open_ext.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.player.play)
        self.pause_btn.clicked.connect(self.player.pause)
        self.loop.toggled.connect(self.player.set_loop)
        self.seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek.sliderReleased.connect(self._seek_release)
        self.open_ext.clicked.connect(self._open_browser)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.loop)
        controls.addWidget(self.seek, 1)
        controls.addWidget(self.open_ext)
        self.player_status = QLabel("")
        self.player_status.setObjectName("muted")
        self.player_status.setWordWrap(True)
        ll.addWidget(self.std_title)
        ll.addWidget(self.std_meta)
        ll.addWidget(self.std_view, 1)
        ll.addLayout(controls)
        ll.addWidget(self.player_status)

        right = QFrame()
        right.setObjectName("card")
        rl = QVBoxLayout(right)
        live_title = QLabel("환자 실시간 영상")
        live_title.setObjectName("sectionTitle")
        self.live_who = QLabel("선택된 환자가 없습니다.")
        self.live_who.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.live_who.setWordWrap(True)
        self.live_view = VideoSurface("카메라를 선택하면 미리보기가 시작됩니다")
        self.live_view.setToolTip("전송 전에 미리보기로 구도를 확인하세요")
        try:
            self.live_view.clicked.disconnect()
        except TypeError:
            pass
        self.live_chip = StatusChip("미리보기 대기", "muted")
        self.send_chip = StatusChip("전송 안 함", "muted")
        self.reply_chip = StatusChip("서버 응답 없음", "muted")
        chips = QHBoxLayout()
        chips.addWidget(self.live_chip)
        chips.addWidget(self.send_chip)
        chips.addWidget(self.reply_chip)
        chips.addStretch()
        send_row = QHBoxLayout()
        self.start_btn = make_button("전송 시작", "primary", "환자 영상과 세션 정보만 서버로 보냅니다. 표준 영상은 보내지 않습니다.")
        self.end_btn = make_button("세션 종료", "danger", "운동 세션과 전송을 끝냅니다.")
        self.start_btn.clicked.connect(self._start)
        self.end_btn.clicked.connect(self._end)
        send_row.addWidget(self.start_btn)
        send_row.addWidget(self.end_btn)
        send_row.addStretch()
        live_note = QLabel("미리보기와 서버 전송은 다르게 표시됩니다. 전송 중에도 이 화면을 떠나면 세션은 유지됩니다.")
        live_note.setObjectName("muted")
        live_note.setWordWrap(True)
        rl.addWidget(live_title)
        rl.addWidget(self.live_who)
        rl.addWidget(self.live_view, 1)
        rl.addLayout(chips)
        rl.addLayout(send_row)
        rl.addWidget(live_note)

        split.addWidget(left, 1)
        split.addWidget(right, 1)

        self.patient_panel = PatientPanel(
            services.patients, session_patient_id_fn=self._session_patient_id
        )
        self.patient_panel.selection_changed.connect(self._on_patient)
        self.patient_panel.change_during_session.connect(self._patient_switch)

        mid = QHBoxLayout()
        mid.addWidget(self.patient_panel, 0)
        mid.addLayout(split, 1)

        plist = QFrame()
        plist.setObjectName("card")
        pl = QVBoxLayout(plist)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("재생목록"))
        self.filter = QComboBox()
        self.search = QLineEdit()
        self.search.setPlaceholderText("제목 검색")
        self.filter.currentIndexChanged.connect(self.reload_playlist)
        self.search.textChanged.connect(self.reload_playlist)
        prow.addWidget(self.filter)
        prow.addWidget(self.search, 1)
        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._select_item)
        actions = QHBoxLayout()
        add_b = make_button("추가", tooltip="표준 운동 영상을 등록합니다.")
        edit_b = make_button("수정")
        del_b = make_button("삭제", tooltip="목록에서만 제거합니다. 원본 파일은 지우지 않습니다.")
        up_b = make_button("위로")
        down_b = make_button("아래로")
        add_b.clicked.connect(self._add_item)
        edit_b.clicked.connect(self._edit_item)
        del_b.clicked.connect(self._del_item)
        up_b.clicked.connect(lambda: self._move(-1))
        down_b.clicked.connect(lambda: self._move(1))
        for b in (add_b, edit_b, del_b, up_b, down_b):
            actions.addWidget(b)
        actions.addStretch()
        pl.addLayout(prow)
        pl.addWidget(self.list, 1)
        pl.addLayout(actions)

        root.addLayout(head)
        root.addLayout(mid, 3)
        root.addWidget(plist, 2)

        self.player.frame_ready.connect(lambda f: self.std_view.set_frame(f))
        self.player.status_text.connect(self.player_status.setText)
        self.player.can_open_external.connect(self._ext)
        self.player.position.connect(self._pos)
        self.player.playing_changed.connect(self._playing)
        services.cameras.frame_ready.connect(self._live_frame)
        services.sessions.session_changed.connect(self._refresh_session)
        services.connection_changed.connect(self._on_conn)
        services.cameras_changed.connect(self.reload_clinical_camera)
        self.reload_clinical_camera()
        self.reload_playlist()
        self._refresh_session()

    def shutdown(self) -> None:
        self.player.shutdown()

    def _session_patient_id(self) -> str | None:
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_EXERCISE:
            return live.patient_id
        return None

    def reload_patients(self) -> None:
        self.patient_panel.reload()

    def reload_clinical_camera(self) -> None:
        cam = clinical_camera(self.services.store.list_cameras())
        if cam is None:
            self.cam_name.setText("운동·보행 카메라 슬롯 없음")
            return
        src = cam.display_source() if cam.device_id or cam.source_kind == "rtsp" else "장치 미지정"
        self.cam_name.setText(f"{cam.name}  ·  {src}")

    def reload_cameras(self) -> None:
        self.reload_clinical_camera()

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

    def reload_playlist(self) -> None:
        current_filter = self.filter.currentText() if self.filter.count() else "전체"
        topics = self.services.store.list_topics()
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem("전체")
        for t in topics:
            self.filter.addItem(t)
        idx = self.filter.findText(current_filter)
        self.filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.filter.blockSignals(False)

        q = self.search.text().strip()
        topic = self.filter.currentText()
        items = self.services.store.list_playlist()
        self.list.clear()
        for item in items:
            if topic != "전체" and item.topic != topic:
                continue
            if q and q not in item.title:
                continue
            status = classify_item(item)
            mark = ""
            if status == MEDIA_MISSING_FILE:
                mark = " · 파일 없음"
            elif status == MEDIA_WEBPAGE:
                mark = " · 외부 열기"
            topic_bit = f" · {item.topic}" if item.topic else ""
            row = QListWidgetItem(f"{item.title}{topic_bit}{mark}")
            row.setData(Qt.ItemDataRole.UserRole, item.id)
            if self._current and self._current.id == item.id:
                font = row.font()
                font.setBold(True)
                row.setFont(font)
            self.list.addItem(row)
        if self.list.count() == 0:
            empty = "재생목록이 없습니다. [추가]로 로컬 파일이나 HTTPS 주소를 등록하세요."
            if q or topic != "전체":
                empty = "조건에 맞는 영상이 없습니다. 필터를 ‘전체’로 바꾸거나 검색어를 지워 보세요."
            self.list.addItem(empty)

    def _selected_id(self) -> str | None:
        item = self.list.currentItem()
        if not item:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _select_item(self) -> None:
        item_id = self._selected_id()
        if not item_id:
            return
        item = self.services.store.get_playlist_item(item_id)
        if not item:
            return
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_EXERCISE and live.playlist_item_id and live.playlist_item_id != item.id:
            if not confirm(
                self,
                "세션 영상 변경",
                "전송 중인 세션의 표준 영상을 바꾸면 메타데이터와 화면이 어긋납니다.\n"
                "지금 세션을 종료한 뒤 영상을 바꿀까요?",
            ):
                self.reload_playlist()
                return
            self.services.sessions.end_clinical("playlist_changed")
        self._current = item
        topic = f"토픽  {item.topic}" if item.topic else "토픽 없음"
        self.std_meta.setText(f"{item.title}  ·  {topic}")
        status = self.player.load(item)
        if status != MEDIA_OK:
            self.std_view.clear_frame()
        self.reload_playlist()

    def _add_item(self) -> None:
        dlg = PlaylistEditor(
            self,
            topics=self.services.store.list_topics(),
            next_sort=self.services.store.next_playlist_sort(),
        )
        if dlg.exec():
            item = dlg.result_item()
            if item:
                self.services.store.save_playlist_item(item)
                self.reload_playlist()

    def _edit_item(self) -> None:
        item_id = self._selected_id()
        if not item_id:
            return
        item = self.services.store.get_playlist_item(item_id)
        if not item:
            return
        dlg = PlaylistEditor(self, item=item, topics=self.services.store.list_topics())
        if dlg.exec():
            result = dlg.result_item()
            if result:
                self.services.store.save_playlist_item(result)
                if self._current and self._current.id == result.id:
                    self._current = result
                    self.player.load(result)
                self.reload_playlist()

    def _del_item(self) -> None:
        item_id = self._selected_id()
        if not item_id:
            return
        if not confirm(self, "목록에서 삭제", "재생목록에서만 제거합니다. 원본 파일은 삭제되지 않습니다."):
            return
        if self._current and self._current.id == item_id:
            live = self.services.sessions.clinical()
            if live and live.playlist_item_id == item_id:
                self.services.sessions.end_clinical("playlist_deleted")
            self.player.stop()
            self._current = None
        self.services.store.delete_playlist_item(item_id)
        self.reload_playlist()

    def _move(self, delta: int) -> None:
        ids = [it.id for it in self.services.store.list_playlist()]
        item_id = self._selected_id()
        if not item_id or item_id not in ids:
            return
        i = ids.index(item_id)
        j = i + delta
        if j < 0 or j >= len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        self.services.store.reorder_playlist(ids)
        self.reload_playlist()

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
                f"진행 중인 {other} 세션을 종료한 뒤 운동 전송을 시작할까요?\n메뉴만 바꿔서는 기존 세션이 끝나지 않습니다.",
            ):
                return
            self.services.sessions.end_clinical("switched")
        ok, reason, sess = self.services.sessions.start_clinical(
            mode=MODE_EXERCISE,
            camera_id=cam_id,
            patient_id=patient.id if patient else None,
            playlist_item_id=self._current.id if self._current else None,
            title=self._current.title if self._current else None,
            topic=self._current.topic if self._current else None,
        )
        if not ok:
            QMessageBox.information(self, "전송을 시작하지 못했습니다", reason)
            return
        self.patient_panel.set_frozen(patient)

    def _end(self) -> None:
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_EXERCISE:
            self.services.sessions.end_clinical("ended")
            self.patient_panel.set_frozen(None)

    def _live_frame(self, frame) -> None:
        cam_id = self._clinical_id()
        if cam_id and frame.camera_id == cam_id:
            self.live_view.set_frame(frame.bgr)

    def _refresh_session(self) -> None:
        live = self.services.sessions.clinical()
        cam_id = self._clinical_id()
        status, detail, seen = self.services.cameras.last_status(cam_id) if cam_id else ("", "", 0)
        sending = bool(live and live.mode == MODE_EXERCISE)
        if sending:
            self.session_chip.set_tone("ok", "운동 세션 전송 중")
            self.live_chip.set_tone("ok", "서버 전송 중")
            self.send_chip.set_tone("ok", "환자 영상 전송 중")
            if live.patient_id:
                try:
                    p = self.services.patients.get(live.patient_id)
                    who = f"세션 대상  {p.display_name}  ·  {p.id}" if p else f"세션 대상  {live.patient_id}"
                except Exception:
                    who = f"세션 대상  {live.patient_id}"
                self.live_who.setText(who)
        else:
            self.session_chip.set_tone("muted", "세션 없음 · 미리보기")
            self.live_chip.set_tone("teal", "미리보기 중")
            self.send_chip.set_tone("muted", "전송 안 함")
        if status in (CAM_DISCONNECTED, CAM_RECONNECTING):
            self.live_chip.set_tone("urgent", CAM_STATUS_LABELS.get(status, status))
            self.live_view.set_overlay(
                "운동·보행 카메라",
                "연결 끊김 · 재연결 또는 장치를 다시 선택하세요",
                disconnected=True,
                last_seen=seen,
            )
            self.retry_cam.setEnabled(True)
        else:
            self.retry_cam.setEnabled(False)
            self.live_view.set_overlay(
                "운동·보행 카메라",
                "서버 전송 중" if sending else "미리보기 중 · 아직 서버로 보내지 않음",
                disconnected=False,
            )
        self.start_btn.setEnabled(not sending)
        self.end_btn.setEnabled(sending)
        self.reload_clinical_camera()

    def tick(self) -> None:
        live = self.services.sessions.clinical()
        if live and live.mode == MODE_EXERCISE:
            sec = int(time.monotonic() - live.started_mono)
            self.elapsed.setText(f"경과 {sec // 60:02d}:{sec % 60:02d}")
        else:
            self.elapsed.setText("경과 00:00")
        self._refresh_session()

    def _on_conn(self, state: str, detail: str) -> None:
        if state in ("connected", "test"):
            tone = "teal" if state == "test" else "ok"
            self.reply_chip.set_tone(tone, "제어 채널 응답 있음" if state == "connected" else "시험 수신기 응답")
        elif state in ("reconnecting", "connecting"):
            self.reply_chip.set_tone("warn", "재연결 중")
        else:
            self.reply_chip.set_tone("muted", "서버 응답 없음")

    def _ext(self, url: str) -> None:
        self._external = url
        self.open_ext.setEnabled(bool(url))

    def _open_browser(self) -> None:
        if self._external:
            QDesktopServices.openUrl(QUrl(self._external))

    def _pos(self, pos: int, duration: int) -> None:
        if self._seeking or duration <= 0:
            return
        self.seek.blockSignals(True)
        self.seek.setValue(int(pos / duration * 1000))
        self.seek.blockSignals(False)

    def _seek_release(self) -> None:
        self._seeking = False
        self.player.seek_ratio(self.seek.value() / 1000.0)

    def _playing(self, playing: bool) -> None:
        self.play_btn.setEnabled(not playing)
        self.pause_btn.setEnabled(playing)
        if playing:
            self.player_status.setText("표준 영상을 재생 중입니다. 이 영상은 서버로 보내지 않습니다.")
