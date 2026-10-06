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
AREAS = ("Tea Field A", "Tea Field B", "Factory Processing", "Packaging Section")

CYCLE_DAYS = 10

DEFAULT_RATES = {
    "above_80": 60.0,
    "between_70_80": 50.0,
    "below_70": 40.0,
    "male_daily": 2000.0,
    "female_daily": 1500.0,
}


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
    SESSION_COOKIE_SECURE = False  # LAN runs over plain HTTP; enable behind HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    RATE_LIMIT_ENABLED = True

    # Lightweight in-process login throttle.
    LOGIN_MAX_FAILURES = 10
    LOGIN_WINDOW_SECONDS = 300


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    RATE_LIMIT_ENABLED = False
