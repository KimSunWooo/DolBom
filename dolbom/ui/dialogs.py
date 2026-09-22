from __future__ import annotations

import uuid
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QUrl
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dolbom.db.store import Store
from dolbom.media.player import classify_item, status_reason
from dolbom.models import (
    PLAYLIST_HTTPS,
    PLAYLIST_LOCAL,
    SOURCE_DEMO,
    SOURCE_DEVICE,
    SOURCE_RTSP,
    SEVERITY_LABELS,
    AppMessage,
    Camera,
    PlaylistItem,
)
from dolbom.theme import set_kind
from dolbom.ui.widgets import make_button


def confirm(parent: QWidget, title: str, text: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    yes = box.button(QMessageBox.StandardButton.Yes)
    yes.setText("확인")
    no = box.button(QMessageBox.StandardButton.No)
    no.setText("취소")
    return box.exec() == QMessageBox.StandardButton.Yes


class CameraEditor(QDialog):
    def __init__(self, parent=None, camera: Camera | None = None, next_sort: int = 0):
        super().__init__(parent)
        self.setWindowTitle("카메라 수정" if camera else "카메라 추가")
        self.camera = camera
        self.next_sort = next_sort
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(camera.name if camera else "")
        self.name.setPlaceholderText("예: 1번 카메라")
        self.location = QLineEdit(camera.location if camera else "")
        self.location.setPlaceholderText("예: 101호 병실")
        self.kind = QComboBox()
        self.kind.addItem("데모 영상", SOURCE_DEMO)
        self.kind.addItem("장치 번호 (웹캠)", SOURCE_DEVICE)
        self.kind.addItem("RTSP 주소", SOURCE_RTSP)
        self.value = QLineEdit(camera.source_value if camera else "warm")
        self.enabled = QCheckBox("사용")
        self.enabled.setChecked(True if camera is None else camera.enabled)
        form.addRow("이름", self.name)
        form.addRow("병실·위치", self.location)
        form.addRow("소스 종류", self.kind)
        form.addRow("장치 번호 / 주소", self.value)
        form.addRow("", self.enabled)
        hint = QLabel("장치 번호는 보통 0(노트북 카메라)부터 시작합니다. RTSP 비밀번호는 로그에 남기지 않습니다.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if camera:
            idx = self.kind.findData(camera.source_kind)
            if idx >= 0:
                self.kind.setCurrentIndex(idx)
        self.kind.currentIndexChanged.connect(self._hint_value)
        self._hint_value()
        self.resize(460, 280)

    def _hint_value(self) -> None:
        kind = self.kind.currentData()
        if kind == SOURCE_DEMO:
            self.value.setPlaceholderText("warm / cool / green / purple")
        elif kind == SOURCE_DEVICE:
            self.value.setPlaceholderText("0")
        else:
            self.value.setPlaceholderText("rtsp://사용자:비밀번호@호스트/경로")

    def result_camera(self) -> Camera | None:
        name = self.name.text().strip()
        if not name:
            return None
        existing = self.camera
        return Camera(
            id=existing.id if existing else str(uuid.uuid4()),
            name=name,
            location=self.location.text().strip(),
            source_kind=self.kind.currentData(),
            source_value=self.value.text().strip() or ("0" if self.kind.currentData() == SOURCE_DEVICE else "warm"),
            enabled=self.enabled.isChecked(),
            sort_order=existing.sort_order if existing else self.next_sort,
        )


class PlaylistEditor(QDialog):
    def __init__(self, parent=None, item: PlaylistItem | None = None, topics: list[str] | None = None, next_sort: int = 0):
        super().__init__(parent)
        self.setWindowTitle("표준 영상 수정" if item else "표준 영상 등록")
        self.item = item
        self.next_sort = next_sort
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(item.title if item else "")
        self.topic = QComboBox()
        self.topic.setEditable(True)
        self.topic.addItem("")
        for t in topics or []:
            if t:
                self.topic.addItem(t)
        if item and item.topic:
            if self.topic.findText(item.topic) < 0:
                self.topic.addItem(item.topic)
            self.topic.setCurrentText(item.topic)
        self.kind = QComboBox()
        self.kind.addItem("로컬 파일", PLAYLIST_LOCAL)
        self.kind.addItem("HTTPS 링크", PLAYLIST_HTTPS)
        self.path = QLineEdit(item.path_or_url if item else "")
        browse = make_button("파일 선택", tooltip="로컬 영상 파일을 선택합니다. 원본은 복사하지 않습니다.")
        browse.clicked.connect(self._browse)
        path_row = QWidget()
        ph = QHBoxLayout(path_row)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.addWidget(self.path, 1)
        ph.addWidget(browse)
        self.desc = QPlainTextEdit(item.description if item else "")
        self.desc.setPlaceholderText("설명 (선택)")
        self.desc.setFixedHeight(80)
        form.addRow("영상 제목", self.title)
        form.addRow("토픽", self.topic)
        form.addRow("소스 종류", self.kind)
        form.addRow("파일 경로 / URL", path_row)
        form.addRow("설명", self.desc)
        hint = QLabel(
            "토픽 예: 어깨운동, 다리운동, 목운동, 종합. 원하는 이름을 그대로 사용할 수 있습니다.\n"
            "유튜브·일반 웹페이지는 등록만 가능하고 내부 재생을 보장하지 않습니다."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(hint)
        if item:
            idx = self.kind.findData(item.source_kind)
            if idx >= 0:
                self.kind.setCurrentIndex(idx)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 380)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "표준 운동 영상 선택", "", "영상 (*.mp4 *.avi *.mkv *.mov *.webm);;모든 파일 (*)"
        )
        if path:
            self.path.setText(path)
            self.kind.setCurrentIndex(self.kind.findData(PLAYLIST_LOCAL))

    def result_item(self) -> PlaylistItem | None:
        title = self.title.text().strip()
        path = self.path.text().strip()
        if not title or not path:
            return None
        existing = self.item
        return PlaylistItem(
            id=existing.id if existing else str(uuid.uuid4()),
            title=title,
            topic=self.topic.currentText().strip(),
            source_kind=self.kind.currentData(),
            path_or_url=path,
            description=self.desc.toPlainText().strip(),
            sort_order=existing.sort_order if existing else self.next_sort,
        )


class MessagesPanel(QDialog):
    jump_to = pyqtSignal(str)
    acknowledged = pyqtSignal()

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("메시지 이력")
        self.setModal(False)
        layout = QVBoxLayout(self)
        hint = QLabel("서버가 보낸 이벤트와 연결 오류를 모읍니다. 시험 메시지는 [시험]으로 표시됩니다.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        self.list = QListWidget()
        self.detail = QLabel("항목을 선택하면 내용이 표시됩니다.")
        self.detail.setWordWrap(True)
        row = QHBoxLayout()
        self.ack_btn = make_button("확인", tooltip="선택한 메시지를 확인 처리합니다.")
        self.ack_all = make_button("모두 확인")
        self.go_btn = make_button("해당 화면 이동", kind="primary")
        self.ack_btn.clicked.connect(self._ack)
        self.ack_all.clicked.connect(self._ack_all)
        self.go_btn.clicked.connect(self._go)
        row.addWidget(self.ack_btn)
        row.addWidget(self.ack_all)
        row.addWidget(self.go_btn)
        row.addStretch()
        layout.addWidget(hint)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.detail)
        layout.addLayout(row)
        self.list.currentItemChanged.connect(self._show)
        self.resize(640, 480)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for msg in self.store.list_messages():
            flag = "미확인" if not msg.acknowledged else "확인"
            test = " · 시험" if msg.is_test else ""
            label = SEVERITY_LABELS.get(msg.severity, "안내")
            item = QListWidgetItem(f"[{flag}{test}] {label}  {msg.occurred_at}  {msg.content[:80]}")
            item.setData(Qt.ItemDataRole.UserRole, msg.event_id)
            self.list.addItem(item)

    def _current(self) -> AppMessage | None:
        item = self.list.currentItem()
        if not item:
            return None
        return next((m for m in self.store.list_messages() if m.event_id == item.data(Qt.ItemDataRole.UserRole)), None)

    def _show(self) -> None:
        msg = self._current()
        if not msg:
            return
        loc = f"위치: {msg.location}" if msg.location else "특정 환자에 연결하지 않음"
        extra = "이 항목은 시험 메시지이며 실제 낙상 이벤트로 기록되지 않습니다." if msg.is_test else ""
        self.detail.setText(f"{msg.content}\n{loc}\n{extra}")

    def _ack(self) -> None:
        msg = self._current()
        if msg:
            self.store.acknowledge(msg.event_id)
            self.reload()
            self.acknowledged.emit()

    def _ack_all(self) -> None:
        self.store.acknowledge_all()
        self.reload()
        self.acknowledged.emit()

    def _go(self) -> None:
        msg = self._current()
        if msg and msg.navigate_to:
            self.jump_to.emit(msg.navigate_to)
            self._ack()
