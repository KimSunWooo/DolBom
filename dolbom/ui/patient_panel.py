"""환자 목록/상세 분리. DB 접근은 PatientRepository만 사용한다."""

from __future__ import annotations

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.qtutil import keep_thread
from dolbom.models import Patient
from dolbom.patients.repository import (
    PatientRepository,
    format_age,
    format_conditions,
    format_date,
    format_room,
    list_label,
)
from dolbom.ui.widgets import StatusChip, make_button


class _QueryThread(QThread):
    listed = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, repo: PatientRepository, token: int, query: str, room: str = ""):
        super().__init__()
        self.repo = repo
        self.token = token
        self.query = query
        self.room = room

    def run(self) -> None:
        try:
            if self.room:
                rows = self.repo.list_in_room(self.room)
            else:
                rows = self.repo.search(self.query)
            self.listed.emit(self.token, rows)
        except Exception as exc:
            self.failed.emit(self.token, str(exc))


class PatientDetail(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.empty = QLabel("환자를 선택하면 상세 정보가 표시됩니다.")
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        self.body = QWidget()
        form = QVBoxLayout(self.body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        self.name = QLabel()
        self.name.setObjectName("sectionTitle")
        self.name.setStyleSheet("font-size: 20px;")
        self.sub = QLabel()
        self.sub.setObjectName("muted")
        form.addWidget(self.name)
        form.addWidget(self.sub)
        self.rows: dict[str, QLabel] = {}
        for key, caption in (
            ("age", "나이"),
            ("admitted", "입실일"),
            ("hospitalized", "입원일"),
            ("room", "병실"),
        ):
            cap = QLabel(caption)
            cap.setObjectName("muted")
            val = QLabel()
            val.setWordWrap(True)
            val.setStyleSheet("font-size: 16px; font-weight: 600;")
            form.addWidget(cap)
            form.addWidget(val)
            self.rows[key] = val
        cond_cap = QLabel("지병 목록")
        cond_cap.setObjectName("muted")
        self.cond_state = QLabel()
        self.cond_list = QListWidget()
        self.cond_list.setMinimumHeight(88)
        form.addWidget(cond_cap)
        form.addWidget(self.cond_state)
        form.addWidget(self.cond_list, 1)
        note = QLabel("환자 ID는 내부 식별용이며 이름을 고유키로 쓰지 않습니다.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addWidget(note)
        layout.addWidget(self.empty)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        self.scroll.hide()

    def show_patient(self, patient: Patient | None) -> None:
        if patient is None:
            self.scroll.hide()
            self.empty.show()
            return
        self.empty.hide()
        self.scroll.show()
        self.name.setText(patient.display_name)
        self.sub.setText(f"환자 ID  {patient.id}")
        self.rows["age"].setText(format_age(patient))
        self.rows["admitted"].setText(format_date(patient.admitted_on))
        self.rows["hospitalized"].setText(format_date(patient.hospitalized_on))
        self.rows["room"].setText(format_room(patient.room))
        state, tags = format_conditions(patient)
        self.cond_state.setText(state)
        self.cond_list.clear()
        if tags:
            for tag in tags:
                self.cond_list.addItem(tag)
        elif state == "지병 없음":
            self.cond_list.addItem("등록된 지병이 없습니다.")
        else:
            self.cond_list.addItem("지병 정보가 등록되지 않았습니다.")


class PatientPanel(QFrame):
    selection_changed = pyqtSignal(object)  # Patient | None
    change_during_session = pyqtSignal(object)

    def __init__(self, repo: PatientRepository, session_patient_id_fn=None):
        super().__init__()
        self.repo = repo
        self._session_id_fn = session_patient_id_fn or (lambda: None)
        self._token = 0
        self._thread: _QueryThread | None = None
        self._selected: Patient | None = None
        self._frozen: Patient | None = None
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        title = QLabel("환자")
        title.setObjectName("sectionTitle")
        self.source = QLabel(repo.source_label)
        self.source.setObjectName("muted")
        self.source.setWordWrap(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("이름, 환자 ID, 병실 검색")
        self.search.textChanged.connect(self.reload)
        self.status = StatusChip("조회 준비", "muted")
        self.retry = make_button("다시 시도")
        self.retry.clicked.connect(self.reload)
        self.retry.hide()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._pick)
        self.session_chip = StatusChip("세션 대상 없음", "muted")
        self.detail = PatientDetail()
        layout.addWidget(title)
        layout.addWidget(self.source)
        layout.addWidget(self.search)
        head = QHBoxLayout()
        head.addWidget(self.status)
        head.addWidget(self.retry)
        head.addStretch()
        layout.addLayout(head)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.session_chip)
        layout.addWidget(self.detail, 1)
        self.setMinimumWidth(300)
        self.reload()

    def selected(self) -> Patient | None:
        return self._selected

    def session_patient(self) -> Patient | None:
        return self._frozen

    def set_frozen(self, patient: Patient | None) -> None:
        self._frozen = patient
        if patient:
            self.session_chip.set_tone("ok", f"세션 고정  {patient.display_name}  ·  {patient.id}")
        else:
            self.session_chip.set_tone("muted", "세션 대상 없음")

    def reload(self) -> None:
        self._token += 1
        token = self._token
        self.status.set_tone("warn", "조회 중")
        self.retry.hide()
        thread = _QueryThread(self.repo, token, self.search.text())
        thread.listed.connect(self._on_list)
        thread.failed.connect(self._on_fail)
        self._thread = keep_thread(self, thread)
        thread.start()

    def _on_list(self, token: int, rows) -> None:
        if token != self._token:
            return
        self.list.clear()
        rows = list(rows)
        if not rows:
            self.status.set_tone("muted", "결과 없음")
            self.list.addItem("조건에 맞는 환자가 없습니다.")
            return
        self.status.set_tone("ok", f"갱신 완료 · {len(rows)}명")
        keep = self._selected.id if self._selected else None
        for patient in rows:
            item = QListWidgetItem(list_label(patient))
            item.setData(Qt.ItemDataRole.UserRole, patient.id)
            item.setToolTip(f"환자 ID {patient.id}")
            self.list.addItem(item)
            if keep and patient.id == keep:
                self.list.setCurrentItem(item)
        if keep is None and self.list.count():
            pass

    def _on_fail(self, token: int, err: str) -> None:
        if token != self._token:
            return
        self.status.set_tone("urgent", "조회 실패")
        self.retry.show()
        self.list.clear()
        self.list.addItem(err)

    def _pick(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        if not pid:
            return
        self._token += 1
        token = self._token
        self.status.set_tone("warn", "상세 조회 중")

        class _Get(QThread):
            ok = pyqtSignal(int, object)
            bad = pyqtSignal(int, str)

            def __init__(self, repo, token, pid):
                super().__init__()
                self.repo, self.token, self.pid = repo, token, pid

            def run(self):
                try:
                    self.ok.emit(self.token, self.repo.get(self.pid))
                except Exception as exc:
                    self.bad.emit(self.token, str(exc))

        worker = _Get(self.repo, token, pid)
        worker.ok.connect(self._on_detail)
        worker.bad.connect(self._on_fail)
        self._thread = keep_thread(self, worker)
        worker.start()

    def _on_detail(self, token: int, patient) -> None:
        if token != self._token:
            return
        self.status.set_tone("ok", "갱신 완료")
        frozen_id = self._session_id_fn()
        if frozen_id and patient and patient.id != frozen_id:
            self.change_during_session.emit(patient)
            return
        self._selected = patient
        self.detail.show_patient(patient)
        self.selection_changed.emit(patient)

    def apply_patient(self, patient: Patient | None) -> None:
        self._selected = patient
        self.detail.show_patient(patient)
        if not patient:
            return
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == patient.id:
                self.list.blockSignals(True)
                self.list.setCurrentItem(item)
                self.list.blockSignals(False)
                break

    def select_id(self, patient_id: str | None) -> None:
        if not patient_id:
            self._selected = None
            self.detail.show_patient(None)
            return
        self._token += 1
        token = self._token

        class _Get(QThread):
            ok = pyqtSignal(int, object)
            bad = pyqtSignal(int, str)

            def __init__(self, repo, token, pid):
                super().__init__()
                self.repo, self.token, self.pid = repo, token, pid

            def run(self):
                try:
                    self.ok.emit(self.token, self.repo.get(self.pid))
                except Exception as exc:
                    self.bad.emit(self.token, str(exc))

        worker = _Get(self.repo, token, patient_id)
        worker.ok.connect(self._on_select_loaded)
        worker.bad.connect(self._on_fail)
        self._thread = keep_thread(self, worker)
        worker.start()

    def _on_select_loaded(self, token: int, patient) -> None:
        if token != self._token:
            return
        self._selected = patient
        self.detail.show_patient(patient)
        if not patient:
            return
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == patient.id:
                self.list.blockSignals(True)
                self.list.setCurrentItem(item)
                self.list.blockSignals(False)
                break


class RoomOccupants(QFrame):
    def __init__(self, repo: PatientRepository):
        super().__init__()
        self.repo = repo
        self._token = 0
        self._thread: _QueryThread | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self.title = QLabel("이 병실 입실 명단")
        self.title.setObjectName("muted")
        self.body = QLabel("병실 정보가 없으면 명단을 조회하지 않습니다.")
        self.body.setWordWrap(True)
        self.note = QLabel("입실 목록일 뿐이며 영상 속 인물과 자동으로 같은 사람으로 보지 않습니다.")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.body)
        layout.addWidget(self.note)

    def load_location(self, location: str) -> None:
        if not (location or "").strip():
            self.body.setText("병실 정보가 없어 입실 명단을 조회하지 않습니다.")
            return
        self._token += 1
        token = self._token
        self.body.setText("입실 명단을 조회하는 중…")
        thread = _QueryThread(self.repo, token, "", location)
        thread.listed.connect(self._fill)
        thread.failed.connect(self._fail)
        self._thread = keep_thread(self, thread)
        thread.start()

    def _fill(self, token: int, rows) -> None:
        if token != self._token:
            return
        rows = list(rows)
        if not rows:
            self.body.setText("이 병실로 등록된 환자가 없습니다.")
            return
        lines = [f"{p.display_name} ({p.id})" for p in rows]
        self.body.setText("\n".join(lines))

    def _fail(self, token: int, err: str) -> None:
        if token != self._token:
            return
        self.body.setText(f"명단을 불러오지 못했습니다. {err}")
