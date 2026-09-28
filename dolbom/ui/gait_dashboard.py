"""보행 질환별 확률 평가 패널. 서버(또는 데모) 값을 표시만 한다."""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dolbom.core.gait_analysis import SLICE_COLORS, empty_analysis
from dolbom.models import GaitAnalysis
from dolbom.theme import INK, INK_MUTED, LINE, SURFACE, TEAL_DEEP


class DonutChart(QWidget):
    def __init__(self):
        super().__init__()
        self._slices: list[tuple[str, float, QColor]] = []
        self._center_title = "대기"
        self._center_value = ""
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, analysis: GaitAnalysis) -> None:
        top = analysis.top() if analysis.source != "none" else None
        if analysis.source == "none" or not top or top.average <= 0:
            self._slices = []
            self._center_title = "분석 없음"
            self._center_value = ""
            self.update()
            return
        self._slices = []
        for row in analysis.conditions:
            if row.average <= 0:
                continue
            color = QColor(SLICE_COLORS.get(row.key, "#6B7280"))
            self._slices.append((row.label, row.average, color))
        short = top.label.split("(")[0].strip()
        self._center_title = short
        self._center_value = f"{top.average:.1f}%"
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 12
        x = (self.width() - side) // 2
        y = (self.height() - side) // 2
        rect = QRect(x, y, side, side)
        if not self._slices:
            painter.setPen(QPen(QColor(LINE), 14))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(18, 18, -18, -18))
            painter.setPen(QColor(INK_MUTED))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._center_title)
            return
        start = 90 * 16
        for _label, value, color in self._slices:
            span = int(round(value / 100.0 * 360 * 16))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPie(rect, start, -span)
            start -= span
        hole = rect.adjusted(int(side * 0.28), int(side * 0.28), -int(side * 0.28), -int(side * 0.28))
        painter.setBrush(QColor(SURFACE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(hole)
        painter.setPen(QColor(INK))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(12)
        painter.setFont(font)
        painter.drawText(hole.adjusted(6, 8, -6, -28), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, self._center_title)
        font.setPointSize(16)
        painter.setFont(font)
        painter.setPen(QColor(TEAL_DEEP))
        painter.drawText(hole.adjusted(6, 28, -6, -8), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._center_value)


class GaitDashboard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        title = QLabel("실시간 분석 대시보드")
        title.setObjectName("sectionTitle")
        self.subtitle = QLabel("질환별 확률 평가")
        self.subtitle.setObjectName("muted")
        self.source_lab = QLabel("분석 결과 없음")
        self.source_lab.setObjectName("muted")
        self.source_lab.setWordWrap(True)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["No.", "병명", "실시간 확률", "누적 확률"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(0)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        donut_lab = QLabel("최종 진단 결과")
        donut_lab.setObjectName("sectionTitle")
        self.donut = DonutChart()
        self.donut.setMinimumSize(200, 200)
        hint = QLabel("각 확률은 독립 평가 뒤 비율로 맞춘 값입니다. 이 프로그램은 낙상·질환을 판정하지 않습니다.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.source_lab)
        layout.addWidget(self.table)
        layout.addWidget(donut_lab)
        layout.addWidget(self.donut, 1)
        layout.addWidget(hint)
        self.show_analysis(empty_analysis())

    def show_analysis(self, analysis: GaitAnalysis) -> None:
        self.source_lab.setText(analysis.note)
        self.table.setRowCount(len(analysis.conditions))
        blank = analysis.source == "none"
        for i, row in enumerate(analysis.conditions):
            no = QTableWidgetItem(str(i + 1))
            name = QTableWidgetItem(row.label)
            rt = QTableWidgetItem("—" if blank else f"{row.realtime:.1f}%")
            avg = QTableWidgetItem("—" if blank else f"{row.average:.1f}%")
            color = QColor(SLICE_COLORS.get(row.key, "#6B7280"))
            no.setForeground(color)
            no.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            rt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            avg.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, no)
            self.table.setItem(i, 1, name)
            self.table.setItem(i, 2, rt)
            self.table.setItem(i, 3, avg)
        header_h = self.table.horizontalHeader().height()
        rows_h = sum(self.table.rowHeight(i) for i in range(self.table.rowCount()))
        self.table.setFixedHeight(header_h + rows_h + 4)
        self.donut.set_data(analysis)
