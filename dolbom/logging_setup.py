"""환자 정보·카메라 비밀번호를 남기지 않는 로컬 로그."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from dolbom.paths import log_dir

_SECRET = re.compile(r"(://[^:/?#]+):([^@/]+)@", re.IGNORECASE)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SECRET.sub(r"\1:****@", record.msg)
        if record.args:
            safe = []
            for arg in record.args:
                if isinstance(arg, str):
                    safe.append(_SECRET.sub(r"\1:****@", arg))
                else:
                    safe.append(arg)
            record.args = tuple(safe)
        return True


def setup_logging() -> None:
    log_file = log_dir() / "dolbom.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.addFilter(_RedactFilter())
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    root = logging.getLogger("dolbom")
    root.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        stream.addFilter(_RedactFilter())
        root.addHandler(stream)
