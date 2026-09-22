import numpy as np

from dolbom.core.capture import open_device_capture
from dolbom.ui.widgets import bgr_to_qimage


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


def test_open_device_reports_busy(monkeypatch):
    monkeypatch.setattr(
        "dolbom.core.capture.describe_device_access",
        lambda path: "다른 프로그램이 이 카메라를 사용 중입니다. 미리보기나 다른 앱을 종료하세요.",
    )
    cap, backend, err = open_device_capture("/dev/video0")
    assert cap is None
    assert "다른 프로그램" in err


def test_odd_width_qimage_is_valid():
    frame = np.zeros((12, 3, 3), dtype=np.uint8)
    image = bgr_to_qimage(frame)
    assert not image.isNull()
    assert image.width() == 3
    assert image.height() == 12
