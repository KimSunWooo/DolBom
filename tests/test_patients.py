from datetime import date

from dolbom.models import COND_NONE, COND_UNKNOWN, Patient
from dolbom.patients.repository import (
    InMemoryPatientRepository,
    conditions_from_db,
    format_age,
    format_conditions,
    korean_age,
)


def test_korean_age_before_birthday():
    assert korean_age(date(2000, 12, 31), date(2026, 9, 22)) == 25
    assert korean_age(date(2000, 1, 1), date(2026, 9, 22)) == 26


def test_age_from_birth_vs_given():
    born = Patient(id="1", display_name="A", birth_date="1948-03-12")
    given = Patient(id="2", display_name="B", age_years=64, age_as_of="2026-01-15")
    missing = Patient(id="3", display_name="C")
    assert format_age(born, date(2026, 9, 22)).startswith("만 ")
    assert "64세" in format_age(given)
    assert "기준일" in format_age(given)
    assert format_age(missing) == "미등록"


def test_conditions_none_vs_unknown():
    none = Patient(id="1", display_name="A", conditions_status=COND_NONE)
    unknown = Patient(id="2", display_name="B", conditions_status=COND_UNKNOWN)
    assert format_conditions(none)[0] == "지병 없음"
    assert format_conditions(unknown)[0] == "정보 미등록"


def test_conditions_json():
    items, st = conditions_from_db('["고혈압", "당뇨"]', None)
    assert items == ["고혈압", "당뇨"]
    assert st == "listed"


def test_homonyms_are_distinct():
    repo = InMemoryPatientRepository(
        [
            Patient(id="P-1", display_name="김영희", room="101호", age_years=78),
            Patient(id="P-2", display_name="김영희", room="205호", age_years=64),
        ]
    )
    rows = repo.search("김영희")
    assert len(rows) == 2
    assert {p.id for p in rows} == {"P-1", "P-2"}
    assert repo.get("P-1").room != repo.get("P-2").room


def test_fixture_directory_and_room_list(tmp_path):
    from dolbom.patients.repository import FixturePatientRepository, format_conditions, list_label

    repo = FixturePatientRepository(tmp_path / "p.db")
    rows = repo.search("")
    assert {p.id for p in rows} >= {"P-1001", "P-1002", "P-1006"}
    twins = repo.search("김영희")
    assert len(twins) == 2
    assert twins[0].id != twins[1].id
    assert list_label(twins[0]) != list_label(twins[1])
    none = repo.get("P-1003")
    assert format_conditions(none)[0] == "지병 없음"
    unknown = repo.get("P-1004")
    assert format_conditions(unknown)[0] == "정보 미등록"
    many = repo.get("P-1005")
    assert len(many.conditions) >= 6
    room = repo.list_in_room("101호")
    assert {p.id for p in room} == {"P-1001", "P-1006"}
    repo.set_fail(True)
    try:
        repo.search("")
        assert False, "should fail"
    except RuntimeError:
        pass
    repo.close()
