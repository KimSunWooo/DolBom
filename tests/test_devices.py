from dolbom.core.devices import Endpoint, group_physical, resolve_open_source
from dolbom.models import MATCH_UNSTABLE, SOURCE_DEVICE, Camera


def test_groups_metadata_with_capture():
    parent = "/sys/devices/usb/1-2"
    eps = [
        Endpoint(0, "/dev/video0", "HD Webcam", "usb-1", parent, "usb-HD-index0", "", True, False),
        Endpoint(1, "/dev/video1", "HD Webcam Metadata", "usb-1", parent, "usb-HD-index1", "", False, True),
    ]
    devices = group_physical(eps)
    assert len(devices) == 1
    assert devices[0].index == 0
    assert devices[0].endpoint_count == 2
    assert devices[0].stable_id == "/dev/v4l/by-id/usb-HD-index0"
    assert devices[0].open_path == "/dev/video0"


def test_two_physical_cameras_stay_separate():
    a = Endpoint(0, "/dev/video0", "Cam A", "usb-a", "/devA", "id-A", "", True, False)
    b = Endpoint(2, "/dev/video2", "Cam A", "usb-b", "/devB", "id-B", "", True, False)
    devices = group_physical([a, b])
    assert len(devices) == 2
    assert {d.stable_id for d in devices} == {"/dev/v4l/by-id/id-A", "/dev/v4l/by-id/id-B"}
    assert devices[0].display_name == devices[1].display_name
    assert devices[0].distinguish_label() != devices[1].distinguish_label()


def test_does_not_open_unstable_index():
    cam = Camera(
        id="c",
        name="x",
        location="",
        source_kind=SOURCE_DEVICE,
        source_value="0",
        device_id="unstable:index:0",
        device_path="/dev/video0",
    )
    source, state, detail = resolve_open_source(cam)
    assert source is None
    assert state == MATCH_UNSTABLE
    assert "다시 선택" in detail


def test_resolve_uses_video_node_not_by_id(monkeypatch):
    from dolbom.core import devices as d
    from dolbom.core.devices import PhysicalDevice

    fake = PhysicalDevice(
        stable_id="/dev/v4l/by-id/usb-cam",
        display_name="Cam",
        index=2,
        open_path="/dev/video2",
        unique=True,
        aliases=["/dev/video2"],
    )
    monkeypatch.setattr(d, "list_local_devices", lambda: [fake])
    cam = Camera(
        id="c",
        name="x",
        location="",
        source_kind=SOURCE_DEVICE,
        source_value="2",
        device_id="/dev/v4l/by-id/usb-cam",
        device_path="/dev/v4l/by-id/usb-cam",
    )
    source, state, _ = resolve_open_source(cam)
    assert state == "ok"
    assert source == "/dev/video2"
