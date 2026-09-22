"""QThread가 실행 중에 GC되지 않도록 소유 객체에 붙들어 둔다."""

from __future__ import annotations

import time

from PyQt6.QtCore import QCoreApplication, QThread


def keep_thread(owner, thread):
    bucket = getattr(owner, "_kept_threads", None)
    if bucket is None:
        owner._kept_threads = []
        bucket = owner._kept_threads

    def _drop() -> None:
        try:
            bucket.remove(thread)
        except ValueError:
            pass

    thread.finished.connect(_drop)
    bucket.append(thread)
    return thread


def join_worker(worker: QThread, timeout_ms: int = 2500) -> None:
    """UI 스레드에서 wait()만 하면 워커의 queued signal과 교착할 수 있다."""
    if worker is None:
        return
    for signal_name in ("frame_ready", "status_changed"):
        signal = getattr(worker, signal_name, None)
        if signal is None:
            continue
        try:
            signal.disconnect()
        except TypeError:
            pass
    if not worker.isRunning():
        return
    deadline = time.monotonic() + timeout_ms / 1000.0
    while worker.isRunning() and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.02)
    if worker.isRunning():
        worker.terminate()
        end = time.monotonic() + 0.8
        while worker.isRunning() and time.monotonic() < end:
            QCoreApplication.processEvents()
            time.sleep(0.02)
