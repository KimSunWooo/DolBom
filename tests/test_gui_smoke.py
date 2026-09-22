import os

from PyQt6.QtWidgets import QApplication

from dolbom.core.services import AppServices
from dolbom.theme import apply_theme
from dolbom.ui.main_window import MainWindow
from dolbom.models import MODE_EXERCISE


def test_gui_navigation_keeps_cctv(tmp_path):
    os.environ["DOLBOM_DATA_DIR"] = str(tmp_path)
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    services = AppServices()
    services.store.set_meta("tcp_port", "46757")
    services.store.set_meta("udp_port", "46004")
    services.start()
    win = MainWindow(services)
    win.show()
    assert len(win.cctv_page._cards) == 2
    cam_id = services.store.camera_by_role("cctv_1").id
    clinical = services.store.camera_by_role("clinical").id
    assert services.cameras.is_running(cam_id)
    assert services.cameras.is_running(clinical)
    win.show_page("exercise")
    win.show_page("gait")
    win.show_page("settings")
    win.show_page("cctv")
    assert services.cameras.is_running(cam_id)
    ok, reason = services.sessions.lease.can_start(clinical, MODE_EXERCISE)
    assert ok
    services.sessions.start_clinical(
        mode=MODE_EXERCISE,
        camera_id=clinical,
        patient_id="P-1001",
        playlist_item_id=None,
        title=None,
        topic=None,
    )
    live = services.sessions.clinical()
    assert live.patient_id == "P-1001"
    ok, reason = services.sessions.lease.can_start(clinical, "gait")
    assert not ok
    win.exercise_page.patient_panel.apply_patient(services.patients.get("P-1002"))
    assert services.sessions.clinical().patient_id == "P-1001"

    from dolbom.core.devices import DEMO_DEVICES

    roles = {
        "cctv_1": services.store.camera_by_role("cctv_1"),
        "cctv_2": services.store.camera_by_role("cctv_2"),
        "clinical": services.store.camera_by_role("clinical"),
    }
    assert len({c.device_id for c in roles.values()}) == 3
    ok, reason = services.assign_device(roles["clinical"].id, DEMO_DEVICES[0])
    assert not ok
    assert "할당" in reason
    extra = services.add_cctv_slot()
    ok, reason = services.assign_device(extra.id, DEMO_DEVICES[3])
    assert ok
    assert services.store.get_camera(extra.id).device_id == "demo:purple"
    assert extra.role == "cctv_3"
    twins = services.patients.search("김영희")
    assert len(twins) == 2

    win.exercise_page.shutdown()
    services.shutdown()
