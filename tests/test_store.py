from pathlib import Path

from dolbom.db.store import Store
from dolbom.models import (
    MSG_INFO,
    MSG_URGENT,
    PLAYLIST_LOCAL,
    SOURCE_DEMO,
    AppMessage,
    Camera,
    PlaylistItem,
    now_iso,
)


def test_seed_and_camera_crud(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    cams = store.list_cameras()
    assert len(cams) == 3
    roles = {c.role for c in cams}
    assert "cctv_1" in roles and "cctv_2" in roles and "clinical" in roles
    extra = Camera(
        id="cam-extra",
        name="병실 CCTV 3",
        location="205호",
        source_kind=SOURCE_DEMO,
        source_value="purple",
        sort_order=store.next_camera_sort(),
        role=store.next_cctv_role(),
    )
    store.save_camera(extra)
    assert extra.role == "cctv_3"
    assert len(store.list_cameras()) == 4
    extra.enabled = False
    store.save_camera(extra)
    assert len(store.list_cameras(include_disabled=False)) == 3


def test_playlist_persists(tmp_path: Path):
    db = tmp_path / "t.db"
    store = Store(db)
    item = PlaylistItem(
        id="p1",
        title="어깨 올리기",
        topic="어깨운동",
        source_kind=PLAYLIST_LOCAL,
        path_or_url="/tmp/missing.mp4",
        sort_order=0,
    )
    store.save_playlist_item(item)
    store.close()
    store2 = Store(db)
    items = store2.list_playlist()
    assert any(i.title == "어깨 올리기" and i.topic == "어깨운동" for i in items)
    assert "어깨운동" in store2.list_topics()
    store2.delete_playlist_item("p1")
    assert store2.get_playlist_item("p1") is None


def test_message_dedupe_and_test_flag(tmp_path: Path):
    store = Store(tmp_path / "t.db")
    msg = AppMessage(
        event_id="e1",
        severity=MSG_URGENT,
        occurred_at=now_iso(),
        content="시험이 아닌 척하면 안 됨",
        is_test=True,
    )
    assert store.upsert_message(msg) is True
    assert store.upsert_message(msg) is False
    loaded = store.list_messages()[0]
    assert loaded.is_test is True
    assert store.unread_count() == 1
    store.acknowledge("e1")
    assert store.unread_count() == 0
