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
    services.start()
    win = MainWindow(services)
    win.show()
    assert len(win.cctv_page._cards) == 2
    cam_id = services.store.list_cameras()[0].id
    assert services.cameras.is_running(cam_id)
    win.show_page("exercise")
    win.show_page("gait")
    win.show_page("settings")
    win.show_page("cctv")
    assert services.cameras.is_running(cam_id)
    ok, reason = services.sessions.lease.can_start(cam_id, MODE_EXERCISE)
    assert ok
    services.sessions.start_clinical(
        mode=MODE_EXERCISE,
        camera_id=cam_id,
        patient_id=None,
        playlist_item_id=None,
        title=None,
        topic=None,
    )
    ok, reason = services.sessions.lease.can_start(cam_id, "gait")
    assert not ok
    win.exercise_page.shutdown()
    services.shutdown()
