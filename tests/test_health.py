"""The unauthenticated health probe used by the hosting platform."""
from __future__ import annotations

from app import create_app
from config import TestConfig


def test_health_check_is_public_and_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_health_check_reports_an_unusable_database(tmp_path):
    class Config(TestConfig):
        # The parent directory does not exist, so opening the database fails.
        DATABASE = str(tmp_path / "missing" / "tea.sqlite3")

    client = create_app(Config).test_client()
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.get_json() == {"status": "unhealthy"}
