"""User CRUD, role matrix, password handling, and deletion safeguards."""
from __future__ import annotations

import db as db_module


def test_role_matrix_for_listing(client, owner_client, supervisor_client, servant_client):
    assert client.get("/api/users").status_code == 401
    assert servant_client.get("/api/users").status_code == 403

    owner_users = owner_client.get("/api/users").get_json()["users"]
    assert len(owner_users) == 7

    supervisor_users = supervisor_client.get("/api/users").get_json()["users"]
    assert supervisor_users and all(user["role"] == "servant" for user in supervisor_users)

    filtered = supervisor_client.get("/api/users?role=owner").get_json()["users"]
    assert filtered == []


def test_supervisor_can_register_servant_only(supervisor_client):
    response = supervisor_client.post(
        "/api/users",
        json={
            "name": "New Collector",
            "role": "servant",
            "gender": "Male",
            "phone": "0770000401",
            "password": "secret123",
            "work_type": "Tea Collector",
        },
    )
    assert response.status_code == 201
    assert response.get_json()["user"]["work_type"] == "Tea Collector"

    blocked = supervisor_client.post(
        "/api/users",
        json={
            "name": "Another Supervisor",
            "role": "supervisor",
            "gender": "Female",
            "phone": "0770000402",
            "password": "secret123",
        },
    )
    assert blocked.status_code == 403


def test_create_requires_servant_work_type(owner_client):
    response = owner_client.post(
        "/api/users",
        json={
            "name": "No Work Type",
            "role": "servant",
            "gender": "Male",
            "phone": "0770000403",
            "password": "secret123",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_choice"


def test_duplicate_phone_rejected(owner_client):
    response = owner_client.post(
        "/api/users",
        json={
            "name": "Copy Cat",
            "role": "servant",
            "gender": "Male",
            "phone": "0770000301",
            "password": "secret123",
            "work_type": "Retail Worker",
        },
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == "duplicate_phone"


def test_edit_without_password_keeps_old_one(owner_client, app):
    response = owner_client.put("/api/users/301", json={"name": "Renamed Collector"})
    assert response.status_code == 200
    assert response.get_json()["user"]["name"] == "Renamed Collector"

    fresh = app.test_client()
    login = fresh.post(
        "/api/auth/login", json={"phone": "0770000301", "password": "servant123"}
    )
    assert login.status_code == 200


def test_edit_with_password_replaces_it(owner_client, app):
    owner_client.put("/api/users/301", json={"password": "brandnew123"})
    fresh = app.test_client()
    assert (
        fresh.post(
            "/api/auth/login", json={"phone": "0770000301", "password": "servant123"}
        ).status_code
        == 401
    )
    assert (
        fresh.post(
            "/api/auth/login", json={"phone": "0770000301", "password": "brandnew123"}
        ).status_code
        == 200
    )


def test_servant_self_service_is_limited(servant_client):
    ok = servant_client.put("/api/users/301", json={"name": "My New Name"})
    assert ok.status_code == 200

    denied = servant_client.put("/api/users/301", json={"work_type": "Retail Worker"})
    assert denied.status_code == 403

    other = servant_client.put("/api/users/302", json={"name": "Hacked"})
    assert other.status_code == 403


def test_supervisor_edit_scope(owner_client, supervisor_client):
    assert supervisor_client.put("/api/users/301", json={"phone": "0770000999"}).status_code == 200
    assert supervisor_client.put("/api/users/101", json={"name": "Nope"}).status_code == 403

    # A supervisor may edit their own basic details, but not another supervisor.
    created = owner_client.post(
        "/api/users",
        json={
            "name": "Second Supervisor",
            "role": "supervisor",
            "gender": "Female",
            "phone": "0770000202",
            "password": "super123",
            "area": "Tea Field B",
        },
    )
    assert created.status_code == 201
    other_supervisor_id = created.get_json()["user"]["user_id"]
    assert (
        supervisor_client.put(
            f"/api/users/{other_supervisor_id}", json={"name": "Nope"}
        ).status_code
        == 403
    )
    assert supervisor_client.put("/api/users/201", json={"name": "Kamal S."}).status_code == 200


def test_delete_requires_owner_and_no_history(owner_client, supervisor_client, row_count):
    assert supervisor_client.delete("/api/users/302").status_code == 403

    before = row_count("users")
    assert owner_client.delete("/api/users/302").status_code == 204
    assert row_count("users") == before - 1


def test_delete_blocked_by_payroll_history(owner_client, make_run):
    make_run()
    response = owner_client.delete("/api/users/301")
    assert response.status_code == 409
    assert response.get_json()["code"] == "has_payroll_history"


def test_cannot_delete_self(owner_client):
    response = owner_client.delete("/api/users/101")
    assert response.status_code == 409
    assert response.get_json()["code"] == "self_delete"


def test_last_owner_cannot_be_deactivated(owner_client):
    response = owner_client.put("/api/users/101", json={"is_active": False})
    assert response.status_code == 409
    assert response.get_json()["code"] == "last_owner"


def test_deactivate_and_reactivate_user(owner_client, row_count):
    assert owner_client.put("/api/users/304", json={"is_active": False}).status_code == 200
    users = owner_client.get("/api/users?role=servant").get_json()["users"]
    target = next(user for user in users if user["user_id"] == 304)
    assert target["is_active"] is False

    assert owner_client.put("/api/users/304", json={"is_active": True}).status_code == 200


def test_servant_can_read_own_profile_only(servant_client):
    assert servant_client.get("/api/users/301").status_code == 200
    assert servant_client.get("/api/users/302").status_code == 403


def test_role_change_requires_owner(owner_client, supervisor_client):
    assert (
        owner_client.put("/api/users/301", json={"role": "supervisor"}).status_code == 200
    )
    user = owner_client.get("/api/users/301").get_json()["user"]
    assert user["role"] == "supervisor"
    assert user["work_type"] is None


# ---------------------------------------------------------------------------
# Supervisor operational sections
# ---------------------------------------------------------------------------
def _new_supervisor(owner_client, phone, **overrides):
    payload = {
        "name": "Multi Section",
        "role": "supervisor",
        "gender": "Female",
        "phone": phone,
        "password": "secret123",
    }
    payload.update(overrides)
    return owner_client.post("/api/users", json=payload)


def test_create_supervisor_with_multiple_sections(owner_client):
    response = _new_supervisor(
        owner_client,
        "0770000501",
        sections=[
            "Packaging Section",
            "Tea Field B",
            "Tea Field A",
            "Factory Processing",
        ],
    )
    assert response.status_code == 201, response.get_json()
    user = response.get_json()["user"]
    # Canonical order, not insertion order, keeps lists stable.
    assert user["sections"] == [
        "Tea Field A",
        "Tea Field B",
        "Factory Processing",
        "Packaging Section",
    ]
    assert user["area"] == "Tea Field A"  # legacy mirror

    listed = owner_client.get("/api/users?role=supervisor").get_json()["users"]
    by_id = {row["user_id"]: row for row in listed}
    assert by_id[user["user_id"]]["sections"] == user["sections"]

    fetched = owner_client.get(f"/api/users/{user['user_id']}").get_json()["user"]
    assert fetched["sections"] == user["sections"]


def test_section_selection_is_deduplicated(owner_client):
    response = _new_supervisor(
        owner_client,
        "0770000502",
        sections=["Tea Field A", "Tea Field A", "Tea Field B"],
    )
    assert response.status_code == 201
    assert response.get_json()["user"]["sections"] == ["Tea Field A", "Tea Field B"]


def test_invalid_section_selection_is_rejected(owner_client):
    unknown = _new_supervisor(owner_client, "0770000503", sections=["Nowhere"])
    assert unknown.status_code == 400
    assert unknown.get_json()["code"] == "invalid_choice"

    not_a_list = _new_supervisor(owner_client, "0770000504", sections="Tea Field A")
    assert not_a_list.status_code == 400
    assert not_a_list.get_json()["code"] == "invalid_sections"

    non_string = _new_supervisor(owner_client, "0770000505", sections=["Tea Field A", 7])
    assert non_string.status_code == 400
    assert non_string.get_json()["code"] == "invalid_sections"


def test_edit_supervisor_adds_and_removes_sections(owner_client, app):
    # Fixture supervisor 201 starts with one section.
    first = owner_client.put(
        "/api/users/201",
        json={"sections": ["Tea Field A", "Factory Processing"]},
    )
    assert first.status_code == 200
    assert first.get_json()["user"]["sections"] == ["Tea Field A", "Factory Processing"]

    # A phone-only edit must not clear the assignments.
    phone_only = owner_client.put("/api/users/201", json={"phone": "0770000299"})
    assert phone_only.status_code == 200
    assert phone_only.get_json()["user"]["sections"] == [
        "Tea Field A",
        "Factory Processing",
    ]

    removed = owner_client.put(
        "/api/users/201", json={"sections": ["Factory Processing"]}
    )
    assert removed.status_code == 200
    assert removed.get_json()["user"]["sections"] == ["Factory Processing"]
    assert removed.get_json()["user"]["area"] == "Factory Processing"

    cleared = owner_client.put("/api/users/201", json={"sections": []})
    assert cleared.status_code == 200
    assert cleared.get_json()["user"]["sections"] == []
    assert cleared.get_json()["user"]["area"] is None

    with app.app_context():
        assert (
            db_module.query_one(
                "SELECT COUNT(*) AS n FROM supervisor_sections WHERE supervisor_id = 201"
            )["n"]
            == 0
        )


def test_legacy_area_field_still_creates_one_section(owner_client):
    response = _new_supervisor(owner_client, "0770000506", area="Packaging Section")
    assert response.status_code == 201
    user = response.get_json()["user"]
    assert user["sections"] == ["Packaging Section"]
    assert user["area"] == "Packaging Section"

    updated = owner_client.put(
        f"/api/users/{user['user_id']}", json={"area": "Tea Field B"}
    )
    assert updated.status_code == 200
    assert updated.get_json()["user"]["sections"] == ["Tea Field B"]


def test_leaving_the_supervisor_role_clears_sections(owner_client, app):
    response = owner_client.put(
        "/api/users/201", json={"role": "servant", "work_type": "Tea Collector"}
    )
    assert response.status_code == 200
    assert response.get_json()["user"]["sections"] == []
    assert response.get_json()["user"]["area"] is None

    with app.app_context():
        assert (
            db_module.query_one(
                "SELECT COUNT(*) AS n FROM supervisor_sections WHERE supervisor_id = 201"
            )["n"]
            == 0
        )


def test_sections_do_not_change_role_permissions(owner_client, supervisor_client):
    """Section assignments are informational; authorization stays role-based."""
    owner_client.put(
        "/api/users/201",
        json={"sections": ["Tea Field A", "Tea Field B", "Packaging Section"]},
    )

    # Still allowed: the supervisor's normal operational surface.
    assert supervisor_client.get("/api/users?role=servant").status_code == 200
    assert supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 303,
            "date": "2026-09-28",
            "original_weight": 10,
            "rainy_day": False,
            "area": "Tea Field A",
        },
    ).status_code == 201

    # Still forbidden: owner-only management and payroll.
    assert supervisor_client.post(
        "/api/users",
        json={
            "name": "Sneaky",
            "role": "supervisor",
            "gender": "Male",
            "phone": "0770000507",
            "password": "secret123",
            "sections": ["Tea Field A"],
        },
    ).status_code == 403
    assert supervisor_client.get(
        "/api/reports/overview?start=2026-09-24&end=2026-10-03"
    ).status_code == 403
    assert supervisor_client.get("/api/payroll/runs").status_code == 403
