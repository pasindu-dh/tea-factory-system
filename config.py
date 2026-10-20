"""Application configuration and shared domain constants."""
from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------
ROLES = ("owner", "supervisor", "servant")
GENDERS = ("Male", "Female")
WORK_TYPES = ("Tea Collector", "Retail Worker")
# How a salary line was settled. Validated in the API rather than by a CHECK
# constraint, so adding a method needs no table rebuild.
PAYMENT_METHODS = ("Cash", "Bank Transfer", "Cheque")
AREAS = ("Tea Field A", "Tea Field B", "Factory Processing", "Packaging Section")

CYCLE_DAYS = 10

DEFAULT_RATES = {
    "above_80": 60.0,
    "between_70_80": 50.0,
    "below_70": 40.0,
    "male_daily": 2000.0,
    "female_daily": 1500.0,
}


def _env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable ('1', 'true', 'yes' are truthy)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_or_create_secret_key(instance_path: Path) -> str:
    """Return the session signing key, generating one on first run."""
    env_key = os.environ.get("TEA_FACTORY_SECRET_KEY")
    if env_key:
        return env_key

    key_file = instance_path / "secret_key"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key

    key = secrets.token_hex(32)
    instance_path.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key, encoding="utf-8")
    return key


class Config:
    SECRET_KEY = None  # set by create_app()
    DATABASE = os.environ.get("TEA_FACTORY_DB") or str(INSTANCE_DIR / "tea_factory.sqlite3")

    # Sessions: signed cookie, no server-side session table.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # LAN runs over plain HTTP. Set TEA_FACTORY_SECURE_COOKIES=1 once the app is
    # served over HTTPS, or nobody can stay signed in over plain HTTP.
    SESSION_COOKIE_SECURE = _env_flag("TEA_FACTORY_SECURE_COOKIES")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # Demo passwords are printed on the sign-in screen for seeded demo installs
    # and for local development. Never enable this on a real deployment.
    SHOW_DEMO_CREDENTIALS = _env_flag("TEA_FACTORY_SHOW_DEMO_CREDENTIALS")

    RATE_LIMIT_ENABLED = True

    # Lightweight in-process login throttle.
    LOGIN_MAX_FAILURES = 10
    LOGIN_WINDOW_SECONDS = 300


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    RATE_LIMIT_ENABLED = False
