from dolbom.core.gait_analysis import (
    CONDITION_CATALOG,
    empty_analysis,
    is_cctv_alert,
    make_demo_analysis,
    parse_gait_analysis,
)
from dolbom.models import MSG_INFO, MSG_SERVER_ERROR, MSG_URGENT, AppMessage, now_iso


def test_demo_analysis_is_labeled_and_normalized():
    snap = make_demo_analysis(12.0)
    assert snap.source == "demo"
    assert "실제 진단이 아닙니다" in snap.note
    assert len(snap.conditions) == len(CONDITION_CATALOG)
    total = sum(c.average for c in snap.conditions)
    assert 99.0 <= total <= 101.0
    top = snap.top()
    assert top is not None
    assert top.average == max(c.average for c in snap.conditions)


def test_empty_analysis_is_not_a_diagnosis():
    snap = empty_analysis()
    assert snap.source == "none"
    assert snap.top() is not None
    assert all(c.realtime == 0 and c.average == 0 for c in snap.conditions)


def test_parse_server_payload():
    snap = parse_gait_analysis(
        {
            "type": "gait.analysis",
            "conditions": [
                {"key": "normal", "realtime": 50, "average": 80},
                {"key": "parkinson", "realtime": 10, "average": 5},
            ],
        }
    )
    assert snap is not None
    assert snap.source == "server"
    by_key = {c.key: c for c in snap.conditions}
    assert by_key["normal"].average == 80
    assert by_key["stroke"].average == 0
    assert parse_gait_analysis({"conditions": []}) is None


def test_cctv_alerts_are_separated_from_system_info():
    fall = AppMessage(
        event_id="a",
        severity=MSG_URGENT,
        occurred_at=now_iso(),
        content="낙상 의심",
        navigate_to="cctv",
    )
    info = AppMessage(
        event_id="b",
        severity=MSG_INFO,
        occurred_at=now_iso(),
        content="안내",
        navigate_to="exercise",
    )
    server = AppMessage(
        event_id="c",
        severity=MSG_SERVER_ERROR,
        occurred_at=now_iso(),
        content="서버 오류",
        navigate_to="settings",
    )
    assert is_cctv_alert(fall) is True
    assert is_cctv_alert(info) is False
    assert is_cctv_alert(server) is False
