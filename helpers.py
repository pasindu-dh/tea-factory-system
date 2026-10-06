"""Small shared utilities: API errors, validation, and row serialization."""
from __future__ import annotations

import re
from datetime import date

from flask import jsonify

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


def parse_positive_number(value, field: str, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ApiError(f"{field} must be a number.", 400, "invalid_number")
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
# Serialization
# ---------------------------------------------------------------------------
def serialize_user(row) -> dict:
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "role": row["role"],
        "gender": row["gender"],
        "phone": row["phone"],
        "work_type": row["work_type"],
        "area": row["area"],
        "is_active": bool(row["is_active"]),
        "must_change_password": bool(row["must_change_password"]),
        "created_at": row["created_at"],
    }
