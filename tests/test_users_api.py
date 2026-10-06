"""User CRUD, role matrix, password handling, and deletion safeguards."""
from __future__ import annotations


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
