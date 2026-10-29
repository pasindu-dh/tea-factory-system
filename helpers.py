"""Small shared utilities: API errors, validation, and row serialization."""
from __future__ import annotations

import math
import re
from datetime import date

from flask import jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from config import AREAS
from db import query_all

PHONE_RE = re.compile(r"^[0-9+\- ]{7,15}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ApiError(Exception):
    """Raised anywhere in the API; converted to a JSON error response."""

    def __init__(self, message: str, status: int = 400, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code or "invalid_request"


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def _handle_api_error(err: ApiError):
        return jsonify({"error": err.message, "code": err.code}), err.status

    @app.errorhandler(RequestEntityTooLarge)
    def _handle_too_large(_err):
        return (
            jsonify({"error": "Request body is too large.", "code": "payload_too_large"}),
            413,
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def parse_iso_date(value, field: str = "date") -> str:
    if not value or not isinstance(value, str):
        raise ApiError(f"{field} is required (YYYY-MM-DD).", 400, "missing_date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ApiError(f"{field} must be a valid date (YYYY-MM-DD).", 400, "invalid_date")
    return parsed.isoformat()


def reject_future(value: str, field: str = "date") -> str:
    if date.fromisoformat(value) > date.today():
        raise ApiError(f"{field} cannot be in the future.", 422, "future_date")
    return value


def parse_time(value, field: str = "time"):
    """Return a validated 'HH:MM' string, or None for empty input."""
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    if not TIME_RE.match(value):
        raise ApiError(f"{field} must be a valid time (HH:MM).", 400, "invalid_time")
    return value


def require_str(data: dict, field: str, max_len: int = 120) -> str:
    value = (data.get(field) or "")
    value = str(value).strip()
    if not value:
        raise ApiError(f"{field} is required.", 400, "missing_field")
    if len(value) > max_len:
        raise ApiError(f"{field} must be at most {max_len} characters.", 400, "field_too_long")
    return value


def parse_phone(value) -> str:
    phone = str(value or "").strip()
    if not PHONE_RE.match(phone):
        raise ApiError("phone must be 7-15 digits (may include +, -, spaces).", 400, "invalid_phone")
    return phone


def parse_choice(value, allowed: tuple, field: str) -> str:
    if value not in allowed:
        raise ApiError(
            f"{field} must be one of: {', '.join(allowed)}.", 400, "invalid_choice"
        )
    return value


MAX_NUMBER = 1_000_000_000


def parse_positive_number(value, field: str, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a number.", 400, "invalid_number")
    if not math.isfinite(number) or abs(number) > MAX_NUMBER:
        raise ApiError(f"{field} is outside the supported range.", 400, "invalid_number")
    if allow_zero:
        if number < 0:
            raise ApiError(f"{field} cannot be negative.", 400, "invalid_number")
    elif number <= 0:
        raise ApiError(f"{field} must be greater than zero.", 400, "invalid_number")
    return number


def validate_password(value, field: str = "password") -> str:
    password = str(value or "")
    if len(password) < 6:
        raise ApiError(f"{field} must be at least 6 characters.", 400, "weak_password")
    return password


# ---------------------------------------------------------------------------
# Supervisor sections
# ---------------------------------------------------------------------------
def ordered_sections(values) -> list[str]:
    """Return the selected areas in the canonical AREAS order, de-duplicated."""
    selected = set(values)
    return [area for area in AREAS if area in selected]


def user_sections(user_id: int) -> list[str]:
    """The operational sections assigned to one supervisor (empty if none)."""
    rows = query_all(
        "SELECT area FROM supervisor_sections WHERE supervisor_id = ?", (user_id,)
    )
    return ordered_sections(row["area"] for row in rows)


def user_sections_map(user_ids) -> dict[int, list[str]]:
    """Bulk form of user_sections(), to avoid one query per row in list views."""
    ids = list(user_ids)
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    rows = query_all(
        f"""SELECT supervisor_id, area FROM supervisor_sections
             WHERE supervisor_id IN ({placeholders})""",
        ids,
    )
    grouped: dict[int, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["supervisor_id"], []).append(row["area"])
    return {user_id: ordered_sections(areas) for user_id, areas in grouped.items()}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def serialize_user(row, sections=None) -> dict:
    """Serialize a user row.

    `sections` is only meaningful for supervisors; callers should pass the
    assignment list so non-supervisor rows do not need a lookup.
    """
    role = row["role"]
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "role": role,
        "gender": row["gender"],
        "phone": row["phone"],
        "work_type": row["work_type"],
        # Legacy single-section field: the first assignment, kept for clients
        # that predate multi-section supervisors.
        "area": row["area"],
        "sections": list(sections) if role == "supervisor" and sections else [],
        "is_active": bool(row["is_active"]),
        "must_change_password": bool(row["must_change_password"]),
        "created_at": row["created_at"],
    }
