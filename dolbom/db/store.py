"""SQLite 로컬 저장. 원본 영상 파일은 저장하지 않는다."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from dolbom.models import (
    PLAYLIST_LOCAL,
    SOURCE_DEMO,
    AppMessage,
    Camera,
    Patient,
    PlaylistItem,
    SessionRecord,
    now_iso,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL,
    source_value TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    room TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS playlist_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    topic TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL,
    path_or_url TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    camera_id TEXT,
    patient_id TEXT,
    playlist_item_id TEXT,
    title TEXT,
    topic TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    event_id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    content TEXT NOT NULL,
    camera_id TEXT,
    location TEXT,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    is_test INTEGER NOT NULL DEFAULT 0,
    navigate_to TEXT
);
"""


def _uid() -> str:
    return str(uuid.uuid4())


class Store:
    def __init__(self, db_file: Path):
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_file), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.init_schema()
        self.seed_if_empty()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _execute(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, args)
        return cur

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("schema_version", "1"),
            )
            self._conn.commit()

    def seed_if_empty(self) -> None:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0]
            if n == 0:
                rows = [
                    (_uid(), "1번 카메라", "101호 병실", SOURCE_DEMO, "warm", 1, 0),
                    (_uid(), "2번 카메라", "복도 A", SOURCE_DEMO, "cool", 1, 1),
                ]
                self._conn.executemany(
                    "INSERT INTO cameras(id, name, location, source_kind, source_value, enabled, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            n = self._conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
            if n == 0:
                rows = [
                    (_uid(), "김영희", "101호"),
                    (_uid(), "박철수", "102호"),
                    (_uid(), "이순자", "103호"),
                ]
                self._conn.executemany(
                    "INSERT INTO patients(id, display_name, room) VALUES (?, ?, ?)",
                    rows,
                )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("demo_mode", "1"),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("server_host", "127.0.0.1"),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("tcp_port", "45757"),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("udp_port", "45004"),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("alert_sound", "1"),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("use_test_receiver", "1"),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                ("client_id", _uid()),
            )
            self._conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    def demo_mode(self) -> bool:
        return self.get_meta("demo_mode", "1") == "1"

    def client_id(self) -> str:
        cid = self.get_meta("client_id")
        if not cid:
            cid = _uid()
            self.set_meta("client_id", cid)
        return cid

    # --- cameras ---
    def list_cameras(self, include_disabled: bool = True) -> list[Camera]:
        sql = "SELECT * FROM cameras"
        if not include_disabled:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY sort_order, name"
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        return [self._camera(r) for r in rows]

    def get_camera(self, camera_id: str) -> Optional[Camera]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM cameras WHERE id = ?", (camera_id,)
            ).fetchone()
        return self._camera(row) if row else None

    def save_camera(self, cam: Camera) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO cameras(id, name, location, source_kind, source_value, enabled, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, location=excluded.location, source_kind=excluded.source_kind, "
                "source_value=excluded.source_value, enabled=excluded.enabled, sort_order=excluded.sort_order",
                (
                    cam.id,
                    cam.name,
                    cam.location,
                    cam.source_kind,
                    cam.source_value,
                    1 if cam.enabled else 0,
                    cam.sort_order,
                ),
            )
            self._conn.commit()

    def next_camera_sort(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) FROM cameras"
            ).fetchone()
            return int(row[0]) + 1

    # --- patients ---
    def list_patients(self) -> list[Patient]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM patients ORDER BY room, display_name"
            ).fetchall()
        return [Patient(id=r["id"], display_name=r["display_name"], room=r["room"]) for r in rows]

    def save_patient(self, p: Patient) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO patients(id, display_name, room) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name, room=excluded.room",
                (p.id, p.display_name, p.room),
            )
            self._conn.commit()

    def delete_patient(self, patient_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
            self._conn.commit()

    # --- playlist ---
    def list_playlist(self) -> list[PlaylistItem]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM playlist_items ORDER BY sort_order, title"
            ).fetchall()
        return [self._playlist(r) for r in rows]

    def list_topics(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT topic FROM playlist_items WHERE topic != '' ORDER BY topic"
            ).fetchall()
        return [r["topic"] for r in rows]

    def get_playlist_item(self, item_id: str) -> Optional[PlaylistItem]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM playlist_items WHERE id = ?", (item_id,)
            ).fetchone()
        return self._playlist(row) if row else None

    def save_playlist_item(self, item: PlaylistItem) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO playlist_items(id, title, topic, source_kind, path_or_url, description, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "title=excluded.title, topic=excluded.topic, source_kind=excluded.source_kind, "
                "path_or_url=excluded.path_or_url, description=excluded.description, sort_order=excluded.sort_order",
                (
                    item.id,
                    item.title,
                    item.topic,
                    item.source_kind,
                    item.path_or_url,
                    item.description,
                    item.sort_order,
                ),
            )
            self._conn.commit()

    def delete_playlist_item(self, item_id: str) -> None:
        """목록에서만 제거. 원본 파일은 삭제하지 않는다."""
        with self._lock:
            self._conn.execute("DELETE FROM playlist_items WHERE id = ?", (item_id,))
            self._conn.commit()

    def next_playlist_sort(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) FROM playlist_items"
            ).fetchone()
            return int(row[0]) + 1

    def reorder_playlist(self, ordered_ids: list[str]) -> None:
        with self._lock:
            for i, item_id in enumerate(ordered_ids):
                self._conn.execute(
                    "UPDATE playlist_items SET sort_order = ? WHERE id = ?",
                    (i, item_id),
                )
            self._conn.commit()

    def ensure_sample_playlist(self, items: list[PlaylistItem]) -> None:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM playlist_items").fetchone()[0]
            if n:
                return
            for item in items:
                self._conn.execute(
                    "INSERT INTO playlist_items(id, title, topic, source_kind, path_or_url, description, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.id,
                        item.title,
                        item.topic,
                        item.source_kind or PLAYLIST_LOCAL,
                        item.path_or_url,
                        item.description,
                        item.sort_order,
                    ),
                )
            self._conn.commit()

    # --- sessions ---
    def insert_session(self, rec: SessionRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions(id, mode, camera_id, patient_id, playlist_item_id, title, topic, started_at, ended_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rec.id,
                    rec.mode,
                    rec.camera_id,
                    rec.patient_id,
                    rec.playlist_item_id,
                    rec.title,
                    rec.topic,
                    rec.started_at,
                    rec.ended_at,
                    rec.status,
                ),
            )
            self._conn.commit()

    def end_session(self, session_id: str, ended_at: str, status: str = "ended") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ?, status = ? WHERE id = ?",
                (ended_at, status, session_id),
            )
            self._conn.commit()

    def list_sessions(self, limit: int = 50) -> list[SessionRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            SessionRecord(
                id=r["id"],
                mode=r["mode"],
                camera_id=r["camera_id"],
                patient_id=r["patient_id"],
                playlist_item_id=r["playlist_item_id"],
                title=r["title"],
                topic=r["topic"],
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                status=r["status"],
            )
            for r in rows
        ]

    # --- messages ---
    def upsert_message(self, msg: AppMessage) -> bool:
        """True if newly inserted (not a duplicate event_id)."""
        with self._lock:
            existing = self._conn.execute(
                "SELECT event_id FROM messages WHERE event_id = ?",
                (msg.event_id,),
            ).fetchone()
            if existing:
                return False
            self._conn.execute(
                "INSERT INTO messages(event_id, severity, occurred_at, content, camera_id, location, acknowledged, is_test, navigate_to) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    msg.event_id,
                    msg.severity,
                    msg.occurred_at,
                    msg.content,
                    msg.camera_id,
                    msg.location,
                    1 if msg.acknowledged else 0,
                    1 if msg.is_test else 0,
                    msg.navigate_to,
                ),
            )
            self._conn.commit()
            return True

    def list_messages(self, limit: int = 200) -> list[AppMessage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages ORDER BY occurred_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._message(r) for r in rows]

    def unread_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE acknowledged = 0"
            ).fetchone()
            return int(row[0])

    def acknowledge(self, event_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE messages SET acknowledged = 1 WHERE event_id = ?",
                (event_id,),
            )
            self._conn.commit()

    def acknowledge_all(self) -> None:
        with self._lock:
            self._conn.execute("UPDATE messages SET acknowledged = 1")
            self._conn.commit()

    @staticmethod
    def _camera(r: sqlite3.Row) -> Camera:
        return Camera(
            id=r["id"],
            name=r["name"],
            location=r["location"],
            source_kind=r["source_kind"],
            source_value=r["source_value"],
            enabled=bool(r["enabled"]),
            sort_order=r["sort_order"],
        )

    @staticmethod
    def _playlist(r: sqlite3.Row) -> PlaylistItem:
        return PlaylistItem(
            id=r["id"],
            title=r["title"],
            topic=r["topic"],
            source_kind=r["source_kind"],
            path_or_url=r["path_or_url"],
            description=r["description"],
            sort_order=r["sort_order"],
        )

    @staticmethod
    def _message(r: sqlite3.Row) -> AppMessage:
        return AppMessage(
            event_id=r["event_id"],
            severity=r["severity"],
            occurred_at=r["occurred_at"],
            content=r["content"],
            camera_id=r["camera_id"],
            location=r["location"],
            acknowledged=bool(r["acknowledged"]),
            is_test=bool(r["is_test"]),
            navigate_to=r["navigate_to"],
        )
