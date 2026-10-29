"""Attendance sheet, upsert semantics, server-derived status, and summary."""
from __future__ import annotations

from conftest import EXPECTED_SALARIES, PERIOD_END, PERIOD_START


def test_sheet_lists_every_active_servant(supervisor_client):
    response = supervisor_client.get(f"/api/attendance?date={PERIOD_START.isoformat()}")
    assert response.status_code == 200
    rows = response.get_json()["rows"]
    assert len(rows) == 5

    by_id = {row["servant_id"]: row for row in rows}
    assert by_id[301]["status"] == "Present"
    assert by_id[301]["check_in"] == "07:30"
    assert by_id[304]["status"] == "Absent"


def test_upsert_updates_in_place(owner_client, row_count):
    day = PERIOD_START.isoformat()
    before = row_count("attendance")

    first = owner_client.put(
        f"/api/attendance/304/{day}", json={"check_in": "08:00", "check_out": "17:00"}
    )
    assert first.status_code == 200
    assert first.get_json()["status"] == "Present"
    assert row_count("attendance") == before

    second = owner_client.put(
        f"/api/attendance/304/{day}", json={"check_in": "09:00", "check_out": "16:00"}
    )
    assert second.status_code == 200
    assert row_count("attendance") == before

    sheet = owner_client.get(f"/api/attendance?date={day}").get_json()["rows"]
    row = next(entry for entry in sheet if entry["servant_id"] == 304)
    assert row["check_in"] == "09:00"
    assert row["status"] == "Present"


def test_status_is_derived_from_check_in(owner_client):
    day = "2026-09-30"
    owner_client.put(f"/api/attendance/304/{day}", json={"check_in": "08:00"})
    owner_client.put(f"/api/attendance/304/{day}", json={"check_in": None})
    sheet = owner_client.get(f"/api/attendance?date={day}").get_json()["rows"]
    row = next(entry for entry in sheet if entry["servant_id"] == 304)
    assert row["status"] == "Absent"


def test_validation_errors(owner_client):
    assert owner_client.put("/api/attendance/301/2026-09-24", json={"check_in": "25:00"}).status_code == 400
    assert owner_client.put("/api/attendance/301/2026-09-24", json={"check_in": "not-a-time"}).status_code == 400
    assert (
        owner_client.put(
            "/api/attendance/301/2026-09-24", json={"check_in": "17:00", "check_out": "08:00"}
        ).status_code
        == 422
    )
    assert owner_client.put("/api/attendance/301/2999-01-01", json={"check_in": "08:00"}).status_code == 422


def test_unknown_servant_404(owner_client):
    assert owner_client.put("/api/attendance/999/2026-09-24", json={}).status_code == 404


def test_bulk_update(owner_client):
    response = owner_client.post(
        "/api/attendance/bulk",
        json={
            "date": "2026-09-30",
            "entries": [
                {"servant_id": 301, "check_in": "07:30", "check_out": "17:00"},
                {"servant_id": 304, "check_in": None, "check_out": None},
            ],
        },
    )
    assert response.status_code == 200
    rows = {row["servant_id"]: row for row in response.get_json()["rows"]}
    assert rows[301]["status"] == "Present"
    assert rows[304]["status"] == "Absent"


def test_summary_matches_expected_brackets(owner_client):
    response = owner_client.get(
        f"/api/attendance/summary?start={PERIOD_START.isoformat()}&end={PERIOD_END.isoformat()}"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["period_days"] == 10

    by_id = {row["servant_id"]: row for row in payload["rows"]}
    for servant_id, expected in EXPECTED_SALARIES.items():
        assert by_id[servant_id]["attendance_pct"] == expected["attendance_pct"]
        assert by_id[servant_id]["present_days"] == expected["attendance_pct"] // 10


def test_servant_sees_only_own_history(servant_client):
    response = servant_client.get("/api/attendance/history")
    assert response.status_code == 200
    rows = response.get_json()["rows"]
    assert rows and all(row["servant_id"] == 301 for row in rows)

    forbidden = servant_client.get("/api/attendance/history?servant_id=302")
    assert forbidden.status_code == 403


def test_supervisor_sees_any_history(supervisor_client):
    response = supervisor_client.get("/api/attendance/history?servant_id=302")
    assert response.status_code == 200
    assert all(row["servant_id"] == 302 for row in response.get_json()["rows"])


def test_servant_cannot_open_the_sheet(servant_client):
    assert servant_client.get(f"/api/attendance?date={PERIOD_START.isoformat()}").status_code == 403


def test_summary_rejects_a_future_end_date(supervisor_client):
    from datetime import date, timedelta

    today = date.today()
    tomorrow = today + timedelta(days=1)
    response = supervisor_client.get(
        f"/api/attendance/summary?start={today.isoformat()}&end={tomorrow.isoformat()}"
    )
    assert response.status_code == 422
    assert response.get_json()["code"] == "future_date"


def test_bulk_update_is_atomic(supervisor_client):
    from datetime import date, timedelta

    day = (date.today() - timedelta(days=1)).isoformat()
    response = supervisor_client.post(
        "/api/attendance/bulk",
        json={
            "date": day,
            "entries": [
                {"servant_id": 301, "check_in": "07:30", "check_out": "17:00"},
                {"servant_id": 302, "check_in": "99:99"},
            ],
        },
    )
    assert response.status_code == 400

    sheet = supervisor_client.get(f"/api/attendance?date={day}").get_json()["rows"]
    row = next(entry for entry in sheet if entry["servant_id"] == 301)
    assert row["attendance_id"] is None
    assert row["status"] == "Absent"
