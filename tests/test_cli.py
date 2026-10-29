"""Operator CLI: bootstrap rates, create a real owner, and refuse demo data in production."""
from __future__ import annotations

from app import create_app
from config import TestConfig
from db import query_one

LONG_SECRET = "0123456789abcdef" * 4


def _app(tmp_path, **overrides):
    class Config(TestConfig):
        DATABASE = str(tmp_path / "cli.sqlite3")

    for name, value in overrides.items():
        setattr(Config, name, value)
    return create_app(Config)


def test_init_db_creates_the_default_rates_row(tmp_path):
    application = _app(tmp_path)
    result = application.test_cli_runner().invoke(args=["init-db"])

    assert result.exit_code == 0, result.output
    with application.app_context():
        row = query_one("SELECT * FROM rate_config WHERE id = 1")
    assert row is not None
    assert row["above_80"] == 60.0


def test_create_owner_can_sign_in(tmp_path):
    application = _app(tmp_path)
    runner = application.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0

    result = runner.invoke(
        args=[
            "create-owner",
            "--name",
            "Real Owner",
            "--phone",
            "0771234567",
            "--gender",
            "Male",
        ],
        input="strongpass123\nstrongpass123\n",
    )
    assert result.exit_code == 0, result.output
    assert "strongpass123" not in result.output

    with application.app_context():
        row = query_one("SELECT * FROM users WHERE phone = '0771234567'")
    assert row["role"] == "owner"

    login = application.test_client().post(
        "/api/auth/login", json={"phone": "0771234567", "password": "strongpass123"}
    )
    assert login.status_code == 200


def test_create_owner_rejects_a_duplicate_phone(tmp_path):
    application = _app(tmp_path)
    runner = application.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0
    args = [
        "create-owner",
        "--name",
        "First",
        "--phone",
        "0771234567",
        "--gender",
        "Male",
    ]
    assert runner.invoke(args=args, input="strongpass123\nstrongpass123\n").exit_code == 0

    duplicate = runner.invoke(args=args, input="strongpass123\nstrongpass123\n")
    assert duplicate.exit_code != 0
    assert "already exists" in duplicate.output


def test_production_refuses_to_seed_demo_data(monkeypatch, tmp_path):
    monkeypatch.setenv("TEA_FACTORY_SECRET_KEY", LONG_SECRET)

    class Config(TestConfig):
        DATABASE = str(tmp_path / "prod-cli.sqlite3")
        PRODUCTION = True
        SESSION_COOKIE_SECURE = True

    application = create_app(Config)
    runner = application.test_cli_runner()
    assert runner.invoke(args=["init-db"]).exit_code == 0

    result = runner.invoke(args=["init-db", "--force", "--seed"])
    assert result.exit_code != 0
    assert "Refusing to load demo data" in result.output

    # The guard runs before --force, so the real database was not deleted.
    with application.app_context():
        assert query_one("SELECT COUNT(*) AS n FROM users")["n"] == 0
