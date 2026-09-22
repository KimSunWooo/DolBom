import numpy as np

from dolbom.core.capture import open_device_capture, uses_demo_frames
from dolbom.models import SOURCE_DEMO, SOURCE_DEVICE, Camera
from dolbom.ui.widgets import bgr_to_qimage


def _demo_cam() -> Camera:
    return Camera(
        id="c",
        name="병실 CCTV 1",
        location="101호",
        source_kind=SOURCE_DEMO,
        source_value="warm",
        device_id="demo:warm",
    )


def _device_cam() -> Camera:
    return Camera(
        id="d",
        name="운동·보행 카메라",
        location="재활실",
        source_kind=SOURCE_DEVICE,
        source_value="2",
        device_id="/dev/v4l/by-id/usb-cam",
        device_path="/dev/video2",
        device_name="HD Webcam",
    )


def test_open_device_uses_v4l2(monkeypatch):
    import cv2

    calls = []

    class FakeCap:
        def __init__(self, src, api=None):
            calls.append((src, api))
            self._opened = True

        def isOpened(self):
            return True

        def release(self):
            pass

    monkeypatch.setattr("dolbom.core.capture.describe_device_access", lambda path: "")
    monkeypatch.setattr("dolbom.core.capture.os.path.exists", lambda path: True)
    monkeypatch.setattr("dolbom.core.capture.os.path.realpath", lambda path: path)
    monkeypatch.setattr(cv2, "VideoCapture", FakeCap)
    cap, backend, err = open_device_capture("/dev/video2")
    assert err == ""
    assert backend == "V4L2"
    assert cap is not None
    assert calls == [("/dev/video2", cv2.CAP_V4L2)]


def test_open_device_tries_opencv_before_access_probe(monkeypatch):
    import cv2

    class FakeCap:
        def __init__(self, src, api=None):
            self._opened = True

        def isOpened(self):
            return True

        def release(self):
            pass

    monkeypatch.setattr(
        "dolbom.core.capture.describe_device_access",
        lambda path: "다른 프로그램이 이 카메라를 사용 중입니다. 미리보기나 다른 앱을 종료하세요.",
    )
    monkeypatch.setattr("dolbom.core.capture.os.path.exists", lambda path: True)
    monkeypatch.setattr("dolbom.core.capture.os.path.realpath", lambda path: path)
    monkeypatch.setattr(cv2, "VideoCapture", FakeCap)
    cap, backend, err = open_device_capture("/dev/video2")
    assert cap is not None
    assert err == ""
    assert backend == "V4L2"


def test_open_device_reports_busy(monkeypatch):
    import cv2

    class FailCap:
        def __init__(self, src, api=None):
            self._opened = False

        def isOpened(self):
            return False

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", FailCap)
    monkeypatch.setattr(
        "dolbom.core.capture.describe_device_access",
        lambda path: "다른 프로그램이 이 카메라를 사용 중입니다. 미리보기나 다른 앱을 종료하세요.",
    )
    cap, backend, err = open_device_capture("/dev/video0")
    assert cap is None
    assert "다른 프로그램" in err


def test_demo_off_does_not_play_demo_source():
    cam = _demo_cam()
    assert cam.is_demo_source() is True
    assert uses_demo_frames(cam, True) is True
    assert uses_demo_frames(cam, False) is False


def test_real_device_keeps_live_capture_when_demo_toggled():
    cam = _device_cam()
    assert cam.is_demo_source() is False
    assert uses_demo_frames(cam, True) is False
    assert uses_demo_frames(cam, False) is False


def test_demo_off_worker_skips_demo_source():
    from PyQt6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from dolbom.core.capture import CaptureWorker

    worker = CaptureWorker(_demo_cam(), demo_forced=False)
    assert worker._use_demo() is False
    assert worker._demo_source_without_mode() is True
    assert worker._open() is False
    assert "데모 모드가 꺼져" in worker._match_detail
    assert worker._skip_reconnect is True
    worker._release()


def test_odd_width_qimage_is_valid():
    frame = np.zeros((12, 3, 3), dtype=np.uint8)
    image = bgr_to_qimage(frame)
    assert not image.isNull()
    assert image.width() == 3
    assert image.height() == 12
