import pytest

from dolbom.core.lease import CameraLease


def test_single_session_occupancy():
    lease = CameraLease()
    ok, _ = lease.can_start("cam-a", "exercise")
    assert ok
    lease.acquire("cam-a", "exercise", "s1")
    ok, reason = lease.can_start("cam-a", "gait")
    assert not ok
    assert "종료" in reason
    ok, reason = lease.can_start("cam-b", "gait")
    assert not ok
    lease.release("s1")
    ok, _ = lease.can_start("cam-b", "gait")
    assert ok


def test_release_other_session_ignored():
    lease = CameraLease()
    lease.acquire("cam-a", "exercise", "s1")
    lease.release("other")
    assert lease.holds("exercise")
    lease.release("s1")
    assert not lease.holds("exercise")
