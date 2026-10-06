"""Daily work-area assignments: listing, upsert, bulk save, and clearing."""
from __future__ import annotations

from conftest import PERIOD_START


def test_listing_includes_unassigned_servants(supervisor_client):
    day = PERIOD_START.isoformat()
    response = supervisor_client.get(f"/api/assignments?date={day}")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["rows"]) == 5

    by_id = {row["servant_id"]: row for row in payload["rows"]}
    assert by_id[301]["area"] == "Tea Field A"  # seeded assignment
    assert by_id[302]["area"] is None
    assert payload["areas"]


def test_put_is_unique_per_servant_and_day(supervisor_client, row_count):
    day = "2026-09-30"
    before = row_count("work_area_assignments")

    assert supervisor_client.put(
        f"/api/assignments/302/{day}", json={"area": "Tea Field B"}
    ).status_code == 200
    assert row_count("work_area_assignments") == before + 1

    assert supervisor_client.put(
        f"/api/assignments/302/{day}", json={"area": "Packaging Section"}
    ).status_code == 200
    assert row_count("work_area_assignments") == before + 1

    rows = supervisor_client.get(f"/api/assignments?date={day}").get_json()["rows"]
    row = next(entry for entry in rows if entry["servant_id"] == 302)
    assert row["area"] == "Packaging Section"


def test_bulk_save_and_clear(supervisor_client, row_count):
    day = "2026-10-01"
    response = supervisor_client.post(
        "/api/assignments/bulk",
        json={
            "date": day,
            "entries": [
                {"servant_id": 301, "area": "Factory Processing"},
                {"servant_id": 302, "area": None},
            ],
        },
    )
    assert response.status_code == 200
    results = {row["servant_id"]: row["area"] for row in response.get_json()["rows"]}
    assert results[301] == "Factory Processing"
    assert results[302] is None

    rows = supervisor_client.get(f"/api/assignments?date={day}").get_json()["rows"]
    by_id = {row["servant_id"]: row["area"] for row in rows}
    assert by_id[301] == "Factory Processing"
    assert by_id[302] is None


def test_invalid_area_rejected(supervisor_client):
    response = supervisor_client.put(
        "/api/assignments/301/2026-09-30", json={"area": "Nowhere"}
    )
    assert response.status_code == 400


def test_future_dates_rejected(supervisor_client):
    assert supervisor_client.put(
        "/api/assignments/301/2999-01-01", json={"area": "Tea Field A"}
    ).status_code == 422


def test_servants_cannot_manage_assignments(servant_client):
    assert servant_client.get("/api/assignments?date=2026-09-24").status_code == 403
    assert servant_client.put(
        "/api/assignments/301/2026-09-30", json={"area": "Tea Field A"}
    ).status_code == 403


def test_delete_assignment(supervisor_client):
    day = "2026-10-02"
    supervisor_client.put(f"/api/assignments/301/{day}", json={"area": "Tea Field A"})
    assert supervisor_client.delete(f"/api/assignments/301/{day}").status_code == 204
    rows = supervisor_client.get(f"/api/assignments?date={day}").get_json()["rows"]
    row = next(entry for entry in rows if entry["servant_id"] == 301)
    assert row["area"] is None
