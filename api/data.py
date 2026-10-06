"""Shared row loaders used by the payroll, dashboard, and report modules."""
from __future__ import annotations

from db import query_all, query_one
from helpers import ApiError
from payroll import validate_period


def period_days(start: str, end: str) -> int:
    """Validated inclusive day count; bad ranges become a 400, never a 500."""
    try:
        return validate_period(start, end)
    except ValueError as exc:
        raise ApiError(str(exc), 400, "invalid_period")


def servants(active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM users WHERE role = 'servant'"
    if active_only:
        sql += " AND is_active = 1"
    sql += " ORDER BY name"
    return [dict(row) for row in query_all(sql)]


def attendance_rows() -> list[dict]:
    return [
        dict(row)
        for row in query_all("SELECT servant_id, work_date, status FROM attendance")
    ]


def weight_rows() -> list[dict]:
    return [
        dict(row)
        for row in query_all(
            "SELECT servant_id, work_date, original_weight, adjusted_weight, rainy_day, area FROM weights"
        )
    ]


def latest_period_end() -> str | None:
    row = query_one("SELECT MAX(period_end) AS latest FROM payroll_runs")
    return row["latest"] if row else None
