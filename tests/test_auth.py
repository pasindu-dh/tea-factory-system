"""Authentication, sessions, password handling, and login throttling."""
from __future__ import annotations

import db as db_module
from app import create_app
from auth import _failed_logins
from config import TestConfig
from conftest import seed_fixture_data


def test_me_requires_login(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.get_json()["code"] == "not_authenticated"


def test_login_success_and_session_persists(client):
    response = client.post(
        "/api/auth/login", json={"phone": "0770000001", "password": "owner123"}
    )
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == "owner"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["name"] == "Owner One"


def test_login_wrong_password(client):
    response = client.post(
        "/api/auth/login", json={"phone": "0770000001", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.get_json()["code"] == "invalid_credentials"


def test_login_missing_fields(client):
    assert client.post("/api/auth/login", json={}).status_code == 400


def test_logout_clears_session(owner_client):
    assert owner_client.post("/api/auth/logout").status_code == 204
    assert owner_client.get("/api/auth/me").status_code == 401


def test_deactivated_account_cannot_login(owner_client, client):
    assert (
        owner_client.put("/api/users/304", json={"is_active": False}).status_code == 200
    )
    response = client.post(
        "/api/auth/login", json={"phone": "0770000304", "password": "servant123"}
    )
    assert response.status_code == 403
    assert response.get_json()["code"] == "account_inactive"


def test_change_password_requires_correct_current(owner_client):
    response = owner_client.post(
        "/api/auth/password",
        json={"current_password": "nope", "new_password": "newpass123"},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "wrong_password"


def test_change_password_then_login_with_new_one(owner_client, client):
    response = owner_client.post(
        "/api/auth/password",
        json={"current_password": "owner123", "new_password": "newpass123"},
    )
    assert response.status_code == 204

    login = client.post(
        "/api/auth/login", json={"phone": "0770000001", "password": "newpass123"}
    )
    assert login.status_code == 200


def test_new_password_must_differ(owner_client):
    response = owner_client.post(
        "/api/auth/password",
        json={"current_password": "owner123", "new_password": "owner123"},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "same_password"


def test_short_password_rejected(owner_client):
    response = owner_client.post(
        "/api/auth/password",
        json={"current_password": "owner123", "new_password": "abc"},
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "weak_password"


def test_owner_reset_password_flow(owner_client, client):
    reset = owner_client.post("/api/users/301/reset-password")
    assert reset.status_code == 200
    temp_password = reset.get_json()["temp_password"]
    assert reset.get_json()["must_change_password"] is True

    login = client.post(
        "/api/auth/login", json={"phone": "0770000301", "password": temp_password}
    )
    assert login.status_code == 200

    me = client.get("/api/auth/me")
    assert me.get_json()["user"]["must_change_password"] is True


def test_password_hash_never_returned(owner_client):
    login = owner_client.post(
        "/api/auth/login", json={"phone": "0770000001", "password": "owner123"}
    )
    assert "password_hash" not in login.get_json()["user"]

    users = owner_client.get("/api/users").get_json()["users"]
    assert all("password_hash" not in user for user in users)
    assert "owner123" not in str(users)


def test_login_throttle_after_repeated_failures(tmp_path):
    class Config(TestConfig):
        DATABASE = str(tmp_path / "throttle.sqlite3")
        RATE_LIMIT_ENABLED = True

    application = create_app(Config)
    db_module.init_db(application)
    with application.app_context():
        seed_fixture_data()

    _failed_logins.clear()
    client = application.test_client()
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login", json={"phone": "0770000001", "password": "bad"}
            ).status_code
            == 401
        )

    throttled = client.post(
        "/api/auth/login", json={"phone": "0770000001", "password": "owner123"}
    )
    assert throttled.status_code == 429
    assert throttled.get_json()["code"] == "too_many_attempts"
    _failed_logins.clear()


def test_sign_in_screen_hides_the_demo_credentials_by_default(client):
    response = client.get("/")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "owner123" not in body
    assert "0771112222" not in body
    assert "Default accounts" not in body


def test_sign_in_screen_shows_the_demo_credentials_when_enabled(tmp_path):
    class Config(TestConfig):
        DATABASE = str(tmp_path / "demo.sqlite3")
        SHOW_DEMO_CREDENTIALS = True

    client = create_app(Config).test_client()
    body = client.get("/").get_data(as_text=True)

    assert "Default accounts" in body
    assert "owner123" in body
    assert "0771112222" in body
