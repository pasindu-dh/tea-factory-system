"""Weighing records: server-computed rainy adjustment and access rules."""
from __future__ import annotations

import db as db_module
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


def test_retail_workers_can_be_weighed(supervisor_client, app):
    response = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 303,  # Retail Worker
            "date": "2026-09-28",
            "original_weight": 60,
            "rainy_day": False,
            "area": "Packaging Section",
        },
    )
    assert response.status_code == 201, response.get_json()
    record = response.get_json()["weight"]
    assert record["servant_name"] == "Retail Male"
    assert record["work_type"] == "Retail Worker"
    assert record["adjusted_weight"] == 60.0

    # Weighing a retail worker must never convert their registered work type.
    with app.app_context():
        work_type = db_module.query_one(
            "SELECT work_type FROM users WHERE user_id = 303"
        )["work_type"]
    assert work_type == "Retail Worker"

    listed = supervisor_client.get(
        "/api/weights?date=2026-09-28&servant_id=303"
    ).get_json()["rows"]
    assert len(listed) == 1
    assert listed[0]["adjusted_weight"] == 60.0


def test_retail_worker_rainy_adjustment_is_server_side(supervisor_client):
    response = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 304,  # Retail Worker
            "date": "2026-09-28",
            "original_weight": 100,
            "rainy_day": True,
            "area": "Factory Processing",
            "adjusted_weight": 1,  # must be ignored
        },
    )
    assert response.status_code == 201
    record = response.get_json()["weight"]
    assert record["original_weight"] == 100.0
    assert record["adjusted_weight"] == 95.0
    assert record["rainy_day"] == 1


def test_staff_accounts_cannot_be_weighed(supervisor_client):
    for staff_id in (101, 201):  # owner, supervisor
        response = supervisor_client.post(
            "/api/weights",
            json={
                "servant_id": staff_id,
                "date": "2026-09-28",
                "original_weight": 10,
                "rainy_day": False,
                "area": "Tea Field A",
            },
        )
        assert response.status_code == 404
        assert response.get_json()["code"] == "not_found"


def test_inactive_servant_cannot_be_weighed(owner_client, supervisor_client):
    assert owner_client.put("/api/users/303", json={"is_active": False}).status_code == 200
    response = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 303,
            "date": "2026-09-28",
            "original_weight": 10,
            "rainy_day": False,
            "area": "Tea Field A",
        },
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == "account_inactive"


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
