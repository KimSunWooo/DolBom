"""보행 질환 확률 표시용 데이터. 클라이언트는 진단을 계산하지 않는다."""

from __future__ import annotations

import math
import time
from typing import Any, Optional

from dolbom.models import GaitAnalysis, GaitConditionScore

CONDITION_CATALOG = (
    ("normal", "Normal (정상)"),
    ("parkinson", "Parkinson's (파킨슨)"),
    ("stroke", "Stroke (뇌졸중/편마비)"),
    ("myopathy", "Myopathy (근병증)"),
    ("antalgic", "Antalgic (통증 회피)"),
    ("abnormal", "Abnormal (이상 보행)"),
)

SLICE_COLORS = {
    "normal": "#3C7380",
    "parkinson": "#D98A2B",
    "stroke": "#C44536",
    "myopathy": "#3B6EA8",
    "antalgic": "#7A4E8A",
    "abnormal": "#6B7280",
}


def empty_analysis(note: str = "") -> GaitAnalysis:
    return GaitAnalysis(
        conditions=[
            GaitConditionScore(key=key, label=label, realtime=0.0, average=0.0)
            for key, label in CONDITION_CATALOG
        ],
        source="none",
        updated_at=0.0,
        note=note or "서버에서 보행 분석 결과를 아직 받지 못했습니다.",
    )


def _norm(values: list[float]) -> list[float]:
    total = sum(max(0.0, v) for v in values)
    if total <= 0:
        return [0.0] * len(values)
    return [max(0.0, v) / total * 100.0 for v in values]


def make_demo_analysis(elapsed_s: float) -> GaitAnalysis:
    """데모 모드 전용 합성 확률. 실제 진단이 아니다."""
    wave = math.sin(elapsed_s / 7.0)
    raw_rt = [
        38 + 8 * wave,
        9 - 2 * wave,
        7 + 1.5 * math.sin(elapsed_s / 5.0),
        18 + 3 * math.cos(elapsed_s / 9.0),
        17 - 2.5 * wave,
        11 + 1.2 * math.sin(elapsed_s / 4.0),
    ]
    raw_avg = [
        72 + 6 * math.sin(elapsed_s / 20.0),
        9 + 1.5 * wave,
        3 + 0.8 * math.cos(elapsed_s / 11.0),
        8 + 2 * wave,
        5 + 1.2 * math.sin(elapsed_s / 13.0),
        3 + 0.6 * wave,
    ]
    rt = _norm(raw_rt)
    avg = _norm(raw_avg)
    rows = [
        GaitConditionScore(key=key, label=label, realtime=rt[i], average=avg[i])
        for i, (key, label) in enumerate(CONDITION_CATALOG)
    ]
    return GaitAnalysis(
        conditions=rows,
        source="demo",
        updated_at=time.time(),
        note="데모 합성값 · 실제 진단이 아닙니다. 메인 서버 분석 결과가 아닙니다.",
    )


def parse_gait_analysis(payload: dict[str, Any]) -> Optional[GaitAnalysis]:
    items = payload.get("conditions") or payload.get("scores") or payload.get("realtime")
    if not isinstance(items, list) or not items:
        return None
    by_key: dict[str, GaitConditionScore] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or raw.get("id") or "").strip().lower()
        label = str(raw.get("label") or raw.get("name") or "")
        if not key:
            continue
        try:
            realtime = float(raw.get("realtime", raw.get("percent", raw.get("value", 0))))
            average = float(raw.get("average", raw.get("avg", realtime)))
        except (TypeError, ValueError):
            continue
        catalog = dict(CONDITION_CATALOG)
        by_key[key] = GaitConditionScore(
            key=key,
            label=label or catalog.get(key, key),
            realtime=max(0.0, realtime),
            average=max(0.0, average),
        )
    if not by_key:
        return None
    rows = []
    for key, label in CONDITION_CATALOG:
        rows.append(by_key.get(key) or GaitConditionScore(key=key, label=label, realtime=0.0, average=0.0))
    for key, score in by_key.items():
        if key not in dict(CONDITION_CATALOG):
            rows.append(score)
    return GaitAnalysis(
        conditions=rows,
        source="server",
        updated_at=time.time(),
        note=str(payload.get("note") or "메인 서버에서 받은 보행 분석입니다. 이 프로그램이 진단한 값이 아닙니다."),
    )


def is_cctv_alert(msg) -> bool:
    """병실 CCTV 낙상·특이사항. 일반 시스템 로그와 구분한다."""
    nav = getattr(msg, "navigate_to", None) or ""
    if nav == "cctv":
        return True
    severity = getattr(msg, "severity", "")
    from dolbom.models import MSG_CAMERA_ERROR, MSG_URGENT

    return severity in (MSG_URGENT, MSG_CAMERA_ERROR)
