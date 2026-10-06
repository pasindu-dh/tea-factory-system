"""Shared fixtures: a throwaway database per test with deterministic data.

Fixture data (period 2026-09-24 .. 2026-10-03, rates at defaults):

    servant  role            present/10   weight (adj. kg)   bracket   salary
    301      Tea Collector       10/10          1000.0        100%  >80   60,000
    302      Tea Collector        8/10           400.0         80%  70-80 20,000
    305      Tea Collector        6/10           595.0         60%  <70   23,800
    303      Retail Worker        8/10              —           —          16,000
    304      Retail Worker        0/10              —           —               0

    305's first weighing is rainy: 100 kg raw -> 95 kg adjusted (5 kg deducted).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

import db as db_module
from app import create_app
from config import TestConfig
from db import execute
from payroll import rainy_adjust

PERIOD_START = date(2026, 9, 24)
PERIOD_END = date(2026, 10, 3)
PERIOD_DAYS = 10

PRESENT_DAYS = {301: 10, 302: 8, 305: 6, 303: 8, 304: 0}

USER_ROWS = [
    # user_id, name, role, gender, phone, password, work_type, area
    (101, "Owner One", "owner", "Male", "0770000001", "owner123", None, None),
    (201, "Supervisor One", "supervisor", "Male", "0770000002", "super123", None, "Tea Field A"),
    (301, "Collector Perfect", "servant", "Male", "0770000301", "servant123", "Tea Collector", None),
    (302, "Collector Eighty", "servant", "Male", "0770000302", "servant123", "Tea Collector", None),
    (305, "Collector Sixty", "servant", "Male", "0770000305", "servant123", "Tea Collector", None),
    (303, "Retail Male", "servant", "Male", "0770000303", "servant123", "Retail Worker", None),
    (304, "Retail Female", "servant", "Female", "0770000304", "servant123", "Retail Worker", None),
]

CREDENTIALS = {
    "owner": ("0770000001", "owner123"),
    "supervisor": ("0770000002", "super123"),
    "servant": ("0770000301", "servant123"),
    "servant_305": ("0770000305", "servant123"),
}

EXPECTED_SALARIES = {
    301: {"attendance_pct": 100, "total_weight": 1000.0, "applied_rate": 60.0, "total_salary": 60000},
    302: {"attendance_pct": 80, "total_weight": 400.0, "applied_rate": 50.0, "total_salary": 20000},
    305: {"attendance_pct": 60, "total_weight": 595.0, "applied_rate": 40.0, "total_salary": 23800},
    303: {"attendance_pct": 80, "total_weight": 0.0, "applied_rate": 2000.0, "total_salary": 16000},
    304: {"attendance_pct": 0, "total_weight": 0.0, "applied_rate": 1500.0, "total_salary": 0},
}


def seed_fixture_data() -> None:
    """Insert the deterministic dataset (must run inside an app context)."""
    for user_id, name, role, gender, phone, password, work_type, area in USER_ROWS:
        execute(
            """INSERT INTO users
                   (user_id, name, role, gender, phone, password_hash, work_type, area)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, name, role, gender, phone, generate_password_hash(password), work_type, area),
        )

    execute(
        """INSERT INTO rate_config
               (id, above_80, between_70_80, below_70, male_daily, female_daily)
           VALUES (1, 60, 50, 40, 2000, 1500)"""
    )

    for offset in range(PERIOD_DAYS):
        day = (PERIOD_START + timedelta(days=offset)).isoformat()

        for servant_id, present_days in PRESENT_DAYS.items():
            present = offset < present_days
            execute(
                """INSERT INTO attendance
                       (servant_id, work_date, check_in, check_out, status, recorded_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    servant_id,
                    day,
                    "07:30" if present else None,
                    "17:00" if present else None,
                    "Present" if present else "Absent",
                    201,
                ),
            )

        if offset < PRESENT_DAYS[301]:
            execute(
                """INSERT INTO weights
                       (servant_id, work_date, original_weight, adjusted_weight, rainy_day, area, recorded_by)
                   VALUES (?, ?, ?, ?, 0, 'Tea Field A', 201)""",
                (301, day, 100.0, 100.0),
            )

        if offset < PRESENT_DAYS[302]:
            execute(
                """INSERT INTO weights
                       (servant_id, work_date, original_weight, adjusted_weight, rainy_day, area, recorded_by)
                   VALUES (?, ?, ?, ?, 0, 'Tea Field B', 201)""",
                (302, day, 50.0, 50.0),
            )

        if offset < PRESENT_DAYS[305]:
            is_rainy = offset == 0
            adjusted = rainy_adjust(100.0) if is_rainy else 100.0
            execute(
                """INSERT INTO weights
                       (servant_id, work_date, original_weight, adjusted_weight, rainy_day, area, recorded_by)
                   VALUES (?, ?, ?, ?, ?, 'Tea Field A', 201)""",
                (305, day, 100.0, adjusted, 1 if is_rainy else 0),
            )

    execute(
        """INSERT INTO work_area_assignments (servant_id, work_date, area, assigned_by)
           VALUES (301, ?, 'Tea Field A', 201)""",
        (PERIOD_START.isoformat(),),
    )


@pytest.fixture()
def app(tmp_path):
    class Config(TestConfig):
        DATABASE = str(tmp_path / "test.sqlite3")

    application = create_app(Config)
    db_module.init_db(application)
    with application.app_context():
        seed_fixture_data()
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def _login(client, phone, password):
    response = client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert response.status_code == 200, response.get_json()
    return client


@pytest.fixture()
def owner_client(app):
    return _login(app.test_client(), *CREDENTIALS["owner"])


@pytest.fixture()
def supervisor_client(app):
    return _login(app.test_client(), *CREDENTIALS["supervisor"])


@pytest.fixture()
def servant_client(app):
    return _login(app.test_client(), *CREDENTIALS["servant"])


@pytest.fixture()
def servant_305_client(app):
    return _login(app.test_client(), *CREDENTIALS["servant_305"])


@pytest.fixture()
def row_count(app):
    def _count(table: str) -> int:
        with app.app_context():
            return db_module.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]

    return _count


@pytest.fixture()
def make_run(owner_client):
    """Compile the standard fixture period and return the run payload."""

    def _make(start=PERIOD_START, end=PERIOD_END):
        response = owner_client.post(
            "/api/payroll/runs", json={"start": start.isoformat(), "end": end.isoformat()}
        )
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    return _make
