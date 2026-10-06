"""Weighing records: server-computed rainy adjustment and access rules."""
from __future__ import annotations

from conftest import PERIOD_START


def test_server_ignores_client_adjusted_weight(supervisor_client, app):
    response = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 301,
            "date": "2026-09-28",
            "original_weight": 100,
            "rainy_day": True,
            "area": "Tea Field B",
            "adjusted_weight": 1,  # must be ignored
        },
    )
    assert response.status_code == 201
    record = response.get_json()["weight"]
    assert record["adjusted_weight"] == 95.0
    assert record["original_weight"] == 100.0


def test_preview_endpoint(supervisor_client):
    response = supervisor_client.post(
        "/api/weights/preview", json={"original_weight": 100, "rainy_day": True}
    )
    payload = response.get_json()
    assert payload["adjusted_weight"] == 95.0
    assert payload["deduction"] == 5.0

    dry = supervisor_client.post(
        "/api/weights/preview", json={"original_weight": 50, "rainy_day": False}
    ).get_json()
    assert dry["adjusted_weight"] == 50.0
    assert dry["deduction"] == 0.0


def test_backdated_entry_is_accepted(supervisor_client):
    response = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 301,
            "date": "2026-09-01",
            "original_weight": 42.5,
            "rainy_day": False,
            "area": "Tea Field A",
        },
    )
    assert response.status_code == 201


def test_validation(supervisor_client):
    base = {"servant_id": 301, "date": "2026-09-28", "area": "Tea Field A"}

    assert supervisor_client.post(
        "/api/weights", json={**base, "original_weight": 0, "rainy_day": False}
    ).status_code == 400
    assert supervisor_client.post(
        "/api/weights", json={**base, "original_weight": -5, "rainy_day": False}
    ).status_code == 400
    assert supervisor_client.post(
        "/api/weights", json={**base, "original_weight": 10, "rainy_day": False, "area": "Nowhere"}
    ).status_code == 400
    assert supervisor_client.post(
        "/api/weights",
        json={**base, "date": "2999-01-01", "original_weight": 10, "rainy_day": False},
    ).status_code == 422


def test_only_tea_collectors_can_be_weighed(supervisor_client):
    response = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 303,  # Retail Worker
            "date": "2026-09-28",
            "original_weight": 10,
            "rainy_day": False,
            "area": "Packaging Section",
        },
    )
    assert response.status_code == 422
    assert response.get_json()["code"] == "not_a_collector"


def test_servant_cannot_create_or_delete(supervisor_client, servant_client):
    created = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 301,
            "date": "2026-09-29",
            "original_weight": 20,
            "rainy_day": False,
            "area": "Tea Field A",
        },
    )
    weight_id = created.get_json()["weight"]["weight_id"]

    assert servant_client.post(
        "/api/weights",
        json={
            "servant_id": 301,
            "date": "2026-09-29",
            "original_weight": 20,
            "rainy_day": False,
            "area": "Tea Field A",
        },
    ).status_code == 403
    assert servant_client.delete(f"/api/weights/{weight_id}").status_code == 403
    assert supervisor_client.delete(f"/api/weights/{weight_id}").status_code == 204


def test_servant_lists_only_own_records(servant_305_client):
    response = servant_305_client.get("/api/weights")
    assert response.status_code == 200
    rows = response.get_json()["rows"]
    assert rows and all(row["servant_id"] == 305 for row in rows)


def test_filter_by_date(supervisor_client):
    day = PERIOD_START.isoformat()
    response = supervisor_client.get(f"/api/weights?date={day}")
    rows = response.get_json()["rows"]
    assert rows and all(row["work_date"] == day for row in rows)


def test_servant_can_use_preview_but_not_sheet(servant_client):
    assert servant_client.post(
        "/api/weights/preview", json={"original_weight": 100, "rainy_day": True}
    ).status_code == 403
