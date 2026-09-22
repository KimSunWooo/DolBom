from dolbom.media.player import classify_item, status_reason
from dolbom.models import (
    MEDIA_MISSING_FILE,
    MEDIA_OK,
    MEDIA_WEBPAGE,
    PLAYLIST_HTTPS,
    PLAYLIST_LOCAL,
    PlaylistItem,
)


def _item(kind, path):
    return PlaylistItem(id="x", title="t", topic="종합", source_kind=kind, path_or_url=path)


def test_youtube_is_webpage():
    st = classify_item(_item(PLAYLIST_HTTPS, "https://www.youtube.com/watch?v=abc"))
    assert st == MEDIA_WEBPAGE
    assert "보장하지" in status_reason(st)


def test_direct_mp4_ok():
    st = classify_item(_item(PLAYLIST_HTTPS, "https://example.com/clip.mp4"))
    assert st == MEDIA_OK


def test_missing_local(tmp_path):
    st = classify_item(_item(PLAYLIST_LOCAL, str(tmp_path / "nope.mp4")))
    assert st == MEDIA_MISSING_FILE
