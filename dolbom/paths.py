"""로컬 데이터 경로. 테스트는 DOLBOM_DATA_DIR 로 격리한다."""

from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "dolbom"


def data_dir() -> Path:
    override = os.environ.get("DOLBOM_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    try:
        from PyQt6.QtCore import QStandardPaths

        root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if root:
            path = Path(root)
            if path.name.lower() != APP_NAME:
                path = path / APP_NAME
            path.mkdir(parents=True, exist_ok=True)
            return path
    except Exception:
        pass
    path = Path.home() / ".local" / "share" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "dolbom.db"


def samples_dir() -> Path:
    path = data_dir() / "samples"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
