from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dolbom import protocol as proto
from dolbom.core.services import AppServices
from dolbom.models import MSG_CAMERA_ERROR, MSG_INFO, MSG_SERVER_ERROR, MSG_URGENT
from dolbom.patients.repository import FIXTURE_NOTE
from dolbom.ui.widgets import make_button


class SettingsPage(QWidget):
    def __init__(self, services: AppServices):
        super().__init__()
        self.services = services
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("설정")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        net = QFrame()
        net.setObjectName("card")
        net.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        nv = QVBoxLayout(net)
        nv.setSpacing(8)
        head = QLabel("연결")
        head.setObjectName("sectionTitle")
        self.demo = QCheckBox("데모 모드 (합성 영상 · 실제 카메라와 혼동하지 마세요)")
        self.demo.setChecked(services.store.demo_mode())
        self.use_rx = QCheckBox("로컬 시험 수신기 사용 (메인 서버가 아닙니다)")
        self.use_rx.setChecked(services.store.get_meta("use_test_receiver", "1") == "1")
        self.host = QLineEdit(services.store.get_meta("server_host", "127.0.0.1"))
        self.tcp = QSpinBox()
        self.tcp.setRange(1024, 65535)
        self.tcp.setValue(int(services.store.get_meta("tcp_port", "45757")))
        self.udp = QSpinBox()
        self.udp.setRange(1024, 65535)
        self.udp.setValue(int(services.store.get_meta("udp_port", "45004")))
        self.tcp.setMaximumWidth(140)
        self.udp.setMaximumWidth(140)
        for field in (self.host, self.tcp, self.udp):
            field.setMinimumHeight(40)
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.sound = QCheckBox("중요 알림 소리")
        self.sound.setChecked(services.store.get_meta("alert_sound", "1") == "1")
        save = make_button("연결 설정 저장", "primary", "저장 후 제어 채널과 영상 전송 주소를 다시 적용합니다.")
        save.clicked.connect(self._save_net)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        lab_host = QLabel("서버 주소")
        lab_tcp = QLabel("TCP 제어 포트")
        lab_udp = QLabel("UDP 영상 포트")
        grid.addWidget(lab_host, 0, 0)
        grid.addWidget(self.host, 0, 1)
        grid.addWidget(lab_tcp, 1, 0)
        grid.addWidget(self.tcp, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(lab_udp, 2, 0)
        grid.addWidget(self.udp, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(1, 1)
        proto_note = QLabel(
            f"제어 프로토콜은 초안 v{proto.PROTOCOL_VERSION}입니다. "
            "기존 메인 서버 규격이 없어 시험 수신기로만 검증합니다. "
            "연결되더라도 ‘메인 서버 연동 완료’로 표시하지 않습니다."
        )
        proto_note.setObjectName("muted")
        proto_note.setWordWrap(True)
        nv.addWidget(head)
        nv.addWidget(self.demo)
        nv.addWidget(self.use_rx)
        nv.addLayout(grid)
        nv.addWidget(self.sound)
        nv.addWidget(save, alignment=Qt.AlignmentFlag.AlignLeft)
        nv.addWidget(proto_note)

        people = QFrame()
        people.setObjectName("card")
        pl = QVBoxLayout(people)
        pl.addWidget(QLabel("환자 정보"))
        hint = QLabel(
            "환자 조회·선택은 운동·보행 화면에서 합니다. 등록·수정·삭제는 제공하지 않습니다. "
            f"현재 원본: {FIXTURE_NOTE}"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        self.plist = QListWidget()
        self.plist.setMinimumHeight(110)
        pl.addWidget(hint)
        pl.addWidget(self.plist)

        tests = QFrame()
        tests.setObjectName("card")
        tl = QVBoxLayout(tests)
        tl.addWidget(QLabel("시험 메시지"))
        tnote = QLabel("시험 항목은 이력에 [시험]으로 남고, 실제 낙상 이벤트로 기록되지 않습니다.")
        tnote.setObjectName("muted")
        tnote.setWordWrap(True)
        trow = QHBoxLayout()
        for label, sev in (
            ("시험 안내", MSG_INFO),
            ("시험 카메라 오류", MSG_CAMERA_ERROR),
            ("시험 서버 오류", MSG_SERVER_ERROR),
            ("시험 긴급", MSG_URGENT),
        ):
            b = make_button(label)
            b.clicked.connect(lambda _=False, s=sev: self.services.messages.inject_test(s))
            trow.addWidget(b)
        trow.addStretch()
        tl.addWidget(tnote)
        tl.addLayout(trow)

        hist = QFrame()
        hist.setObjectName("card")
        hl = QVBoxLayout(hist)
        hl.addWidget(QLabel("최근 세션 이력"))
        self.hist = QListWidget()
        self.hist.setMinimumHeight(110)
        hl.addWidget(self.hist)

        root.addWidget(net)
        root.addWidget(people)
        root.addWidget(tests)
        root.addWidget(hist)
        root.addStretch(1)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.reload()

    def reload(self) -> None:
        self.plist.clear()
        try:
            for p in self.services.patients.search(""):
                item = QListWidgetItem(f"{p.display_name}  ·  {p.id}  ·  {p.room or '병실 미등록'}")
                self.plist.addItem(item)
        except Exception as exc:
            self.plist.addItem(f"조회 실패: {exc}")
        self.hist.clear()
        for s in self.services.store.list_sessions(20):
            who = s.patient_id or "대상 미지정"
            self.hist.addItem(f"{s.started_at}  {s.mode}  {s.status}  {who}")

    def _save_net(self) -> None:
        self.services.store.set_meta("demo_mode", "1" if self.demo.isChecked() else "0")
        self.services.store.set_meta("use_test_receiver", "1" if self.use_rx.isChecked() else "0")
        self.services.store.set_meta("server_host", self.host.text().strip() or "127.0.0.1")
        self.services.store.set_meta("tcp_port", str(self.tcp.value()))
        self.services.store.set_meta("udp_port", str(self.udp.value()))
        self.services.store.set_meta("alert_sound", "1" if self.sound.isChecked() else "0")
        self.services.apply_network_settings()
        if not self.demo.isChecked():
            still_demo = [c for c in self.services.store.list_cameras() if c.enabled and c.is_demo_source()]
            if still_demo:
                QMessageBox.information(
                    self,
                    "저장됨",
                    "데모 모드를 껐습니다. 아직 데모 영상이 할당된 카메라가 있어 실영상을 열 수 없습니다. "
                    "병실 CCTV·운동·보행 화면의 [카메라 선택]에서 실제 장치를 지정하세요.",
                )
                return
        QMessageBox.information(self, "저장됨", "연결 설정을 적용했습니다. 데모 모드와 실제 연결 상태는 상단 표시를 확인하세요.")
