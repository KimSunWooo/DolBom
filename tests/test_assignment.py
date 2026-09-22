from dolbom.core.assignment import conflict_for
from dolbom.models import ROLE_CLINICAL, SOURCE_DEMO, Camera


def _cam(**kwargs):
    base = dict(
        id="x",
        name="n",
        location="",
        source_kind=SOURCE_DEMO,
        source_value="warm",
        role="cctv_1",
        device_id="demo:warm",
    )
    base.update(kwargs)
    return Camera(**base)


def test_duplicate_device_blocked():
    cams = [
        _cam(id="a", role="cctv_1", device_id="demo:warm", name="CCTV1"),
        _cam(id="b", role=ROLE_CLINICAL, device_id="demo:green", name="임상"),
    ]
    hit = conflict_for(cams, "b", "demo:warm")
    assert hit is not None
    assert "병실 CCTV 1" in hit.message


def test_same_camera_reassign_ok():
    cams = [_cam(id="a", device_id="demo:warm")]
    assert conflict_for(cams, "a", "demo:warm") is None
