from __future__ import annotations

import argparse
import sys

from PyQt6.QtWidgets import QApplication

from dolbom.core.services import AppServices
from dolbom.logging_setup import setup_logging
from dolbom.theme import apply_theme
from dolbom.ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="돌봄(DolBom) 요양원·재활센터 관리 프로그램")
    parser.add_argument("--demo", action="store_true", help="데모 모드를 강제로 켭니다")
    args, qt_args = parser.parse_known_args(argv)

    setup_logging()
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("돌봄")
    app.setOrganizationName("DolBom")
    apply_theme(app)

    services = AppServices()
    if args.demo:
        services.store.set_meta("demo_mode", "1")
        services.store.set_meta("use_test_receiver", "1")
    services.start()

    window = MainWindow(services)
    window.show()
    code = app.exec()
    return int(code)
