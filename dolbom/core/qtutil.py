"""QThread가 실행 중에 GC되지 않도록 소유 객체에 붙들어 둔다."""

from __future__ import annotations


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
