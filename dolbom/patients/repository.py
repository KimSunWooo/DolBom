"""환자 디렉터리. 위젯은 이 인터페이스만 사용한다."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Protocol

from dolbom.models import (
    COND_LISTED,
    COND_NONE,
    COND_UNKNOWN,
    MISSING,
    Patient,
)


class PatientRepository(Protocol):
    source_label: str

    def search(self, query: str = "") -> list[Patient]:
        ...

    def get(self, patient_id: str) -> Optional[Patient]:
        ...

    def list_in_room(self, room: str) -> list[Patient]:
        ...


def korean_age(birth: date, today: Optional[date] = None) -> int:
    today = today or date.today()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = value.strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def format_date(value: Optional[str]) -> str:
    parsed = parse_date(value)
    if parsed:
        return parsed.isoformat()
    return MISSING if not value else str(value)


def format_age(patient: Patient, today: Optional[date] = None) -> str:
    if patient.birth_date:
        parsed = parse_date(patient.birth_date)
        if parsed:
            return f"만 {korean_age(parsed, today)}세"
    if patient.age_years is not None:
        if patient.age_as_of:
            return f"{patient.age_years}세 (기준일 {format_date(patient.age_as_of)})"
        return f"{patient.age_years}세"
    return MISSING


def format_room(room: str) -> str:
    return room.strip() if room and room.strip() else MISSING


def format_conditions(patient: Patient) -> tuple[str, list[str]]:
    if patient.conditions_status == COND_NONE:
        return "지병 없음", []
    if patient.conditions_status == COND_UNKNOWN and not patient.conditions:
        return "정보 미등록", []
    if patient.conditions:
        return "등록됨", list(patient.conditions)
    return "정보 미등록", []


def list_label(patient: Patient) -> str:
    age = format_age(patient)
    room = format_room(patient.room)
    return f"{patient.display_name}  ·  {age}  ·  {room}"


def conditions_from_db(raw: Optional[str], status: Optional[str]) -> tuple[list[str], str]:
    if status in (COND_NONE, COND_UNKNOWN, COND_LISTED):
        st = status
    elif raw is None:
        st = COND_UNKNOWN
    elif raw.strip() in ("", "[]"):
        st = COND_NONE
    else:
        st = COND_LISTED
    items: list[str] = []
    if raw:
        text = raw.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    items = [str(x).strip() for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                items = [p.strip() for p in text.split(",") if p.strip()]
        else:
            items = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    if items and st == COND_UNKNOWN:
        st = COND_LISTED
    return items, st


FIXTURE_NOTE = "개발용 가상 환자 디렉터리 · 병원 운영 DB가 아닙니다"


_FIXTURE_ROWS = [
    (
        "P-1001",
        "김영희",
        "101호",
        "1948-03-12",
        None,
        None,
        "2024-11-02",
        None,
        json.dumps(["고혈압", "제2형 당뇨"], ensure_ascii=False),
        COND_LISTED,
    ),
    (
        "P-1002",
        "김영희",
        "205호",
        None,
        64,
        "2026-01-15",
        "2025-06-20",
        "2025-06-18",
        json.dumps(["골다공증"], ensure_ascii=False),
        COND_LISTED,
    ),
    (
        "P-1003",
        "박철수",
        "102호",
        "1939-08-01",
        None,
        None,
        "2023-04-10",
        "2023-04-09",
        "[]",
        COND_NONE,
    ),
    (
        "P-1004",
        "이순자",
        "103호",
        None,
        None,
        None,
        None,
        None,
        None,
        COND_UNKNOWN,
    ),
    (
        "P-1005",
        "최민수",
        "",
        None,
        81,
        None,
        "2025-12-01",
        None,
        json.dumps(["심부전", "만성신부전", "골관절염", "불면증", "백내장", "빈혈"], ensure_ascii=False),
        COND_LISTED,
    ),
    (
        "P-1006",
        "정미경",
        "101호",
        "1955-12-30",
        None,
        None,
        "2026-01-08",
        "2026-01-05",
        json.dumps(["치매"], ensure_ascii=False),
        COND_LISTED,
    ),
]


class FixturePatientRepository:
    """로컬 SQLite에 심은 가상 데이터. 실제 병원 스키마가 오면 이 구현만 교체한다."""

    source_label = FIXTURE_NOTE

    def __init__(self, db_file: Path):
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_file), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._fail = False
        self._init()

    def set_fail(self, fail: bool) -> None:
        self._fail = fail

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patient_directory (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    room TEXT NOT NULL DEFAULT '',
                    birth_date TEXT,
                    age_years INTEGER,
                    age_as_of TEXT,
                    admitted_on TEXT,
                    hospitalized_on TEXT,
                    conditions_json TEXT,
                    conditions_status TEXT NOT NULL DEFAULT 'unknown'
                )
                """
            )
            n = self._conn.execute("SELECT COUNT(*) FROM patient_directory").fetchone()[0]
            if n == 0:
                self._conn.executemany(
                    "INSERT INTO patient_directory("
                    "id, display_name, room, birth_date, age_years, age_as_of, "
                    "admitted_on, hospitalized_on, conditions_json, conditions_status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    _FIXTURE_ROWS,
                )
            self._conn.commit()

    def _check(self) -> None:
        if self._fail:
            raise RuntimeError("환자 디렉터리에 연결하지 못했습니다. 네트워크·DB 설정을 확인하세요.")

    def search(self, query: str = "") -> list[Patient]:
        self._check()
        q = query.strip()
        with self._lock:
            if q:
                rows = self._conn.execute(
                    "SELECT * FROM patient_directory WHERE display_name LIKE ? OR id LIKE ? OR room LIKE ? "
                    "ORDER BY display_name, room, id",
                    (f"%{q}%", f"%{q}%", f"%{q}%"),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM patient_directory ORDER BY display_name, room, id"
                ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, patient_id: str) -> Optional[Patient]:
        self._check()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM patient_directory WHERE id = ?", (patient_id,)
            ).fetchone()
        return self._row(row) if row else None

    def list_in_room(self, room: str) -> list[Patient]:
        self._check()
        key = (room or "").strip()
        if not key:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM patient_directory WHERE room != '' ORDER BY display_name, id"
            ).fetchall()
        out = []
        for r in rows:
            patient = self._row(r)
            if _room_match(key, patient.room):
                out.append(patient)
        return out

    @staticmethod
    def _row(r: sqlite3.Row) -> Patient:
        items, status = conditions_from_db(r["conditions_json"], r["conditions_status"])
        age = r["age_years"]
        return Patient(
            id=r["id"],
            display_name=r["display_name"],
            room=r["room"] or "",
            birth_date=r["birth_date"],
            age_years=int(age) if age is not None else None,
            age_as_of=r["age_as_of"],
            admitted_on=r["admitted_on"],
            hospitalized_on=r["hospitalized_on"],
            conditions=items,
            conditions_status=status,
        )


def _room_match(location: str, room: str) -> bool:
    loc = location.replace(" ", "")
    rm = room.replace(" ", "")
    if not rm:
        return False
    return rm in loc or loc in rm or loc == rm


class InMemoryPatientRepository:
    source_label = "테스트용 메모리 디렉터리"

    def __init__(self, patients: list[Patient]):
        self._patients = {p.id: p for p in patients}

    def search(self, query: str = "") -> list[Patient]:
        q = query.strip()
        rows = list(self._patients.values())
        if q:
            rows = [
                p
                for p in rows
                if q in p.display_name or q in p.id or q in (p.room or "")
            ]
        rows.sort(key=lambda p: (p.display_name, p.room, p.id))
        return rows

    def get(self, patient_id: str) -> Optional[Patient]:
        return self._patients.get(patient_id)

    def list_in_room(self, room: str) -> list[Patient]:
        return [p for p in self.search() if _room_match(room, p.room)]
