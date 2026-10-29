"""Production configuration validation fails fast instead of deploying insecurely."""
from __future__ import annotations

import pytest

from app import create_app
from config import TestConfig

LONG_SECRET = "0123456789abcdef" * 4


def _production_config(tmp_path, **overrides):
    class Config(TestConfig):
        PRODUCTION = True
        SESSION_COOKIE_SECURE = True
        SHOW_DEMO_CREDENTIALS = False
        DATABASE = str(tmp_path / "prod.sqlite3")

    for name, value in overrides.items():
        setattr(Config, name, value)
    return Config


def test_production_requires_an_environment_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("TEA_FACTORY_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TEA_FACTORY_SECRET_KEY"):
        create_app(_production_config(tmp_path))


def test_production_rejects_a_short_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("TEA_FACTORY_SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="TEA_FACTORY_SECRET_KEY"):
        create_app(_production_config(tmp_path))


def test_production_rejects_insecure_cookies(monkeypatch, tmp_path):
    monkeypatch.setenv("TEA_FACTORY_SECRET_KEY", LONG_SECRET)
    with pytest.raises(RuntimeError, match="SECURE_COOKIES"):
        create_app(_production_config(tmp_path, SESSION_COOKIE_SECURE=False))


def test_production_rejects_demo_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("TEA_FACTORY_SECRET_KEY", LONG_SECRET)
    with pytest.raises(RuntimeError, match="SHOW_DEMO_CREDENTIALS"):
        create_app(_production_config(tmp_path, SHOW_DEMO_CREDENTIALS=True))


def test_production_accepts_a_valid_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("TEA_FACTORY_SECRET_KEY", LONG_SECRET)
    application = create_app(_production_config(tmp_path))
    assert application.config["PRODUCTION"] is True
