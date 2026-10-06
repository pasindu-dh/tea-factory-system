"""Authentication: hashed passwords, signed-cookie sessions, role enforcement."""
from __future__ import annotations

import time
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, query_one
from helpers import ApiError, serialize_user, validate_password

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# In-process login throttle: {remote_addr: [failure timestamps]}
_failed_logins: dict[str, list[float]] = {}


def current_user() -> dict | None:
    """The logged-in user as a dict, or None. Inactive accounts are rejected."""
    uid = session.get("user_id")
    if uid is None:
        return None
    row = query_one("SELECT * FROM users WHERE user_id = ? AND is_active = 1", (uid,))
    return dict(row) if row else None


def active_user() -> dict:
    """The logged-in user, from the per-request cache when available."""
    user = getattr(g, "current_user", None)
    if user is not None:
        return user
    user = current_user()
    if user is None:
        raise ApiError("Authentication required.", 401, "not_authenticated")
    g.current_user = user
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        g.current_user = active_user()
        return view(*args, **kwargs)

    return wrapped


def require_role(*roles: str):
    """Restrict a view to the given roles; must be applied outside @login_required."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = active_user()
            if user["role"] not in roles:
                raise ApiError(
                    "Your role does not have permission to do this.",
                    403,
                    "forbidden",
                )
            return view(*args, **kwargs)

        return wrapped

    return decorator


# ---------------------------------------------------------------------------
# Login throttle
# ---------------------------------------------------------------------------
def _throttle_key() -> str:
    return request.remote_addr or "unknown"


def _check_throttle() -> None:
    if not current_app.config.get("RATE_LIMIT_ENABLED", True):
        return
    window = current_app.config["LOGIN_WINDOW_SECONDS"]
    max_failures = current_app.config["LOGIN_MAX_FAILURES"]
    now = time.time()
    attempts = [t for t in _failed_logins.get(_throttle_key(), []) if now - t < window]
    _failed_logins[_throttle_key()] = attempts
    if len(attempts) >= max_failures:
        raise ApiError(
            "Too many failed login attempts. Try again in a few minutes.",
            429,
            "too_many_attempts",
        )


def _record_failure() -> None:
    if not current_app.config.get("RATE_LIMIT_ENABLED", True):
        return
    _failed_logins.setdefault(_throttle_key(), []).append(time.time())


def _clear_failures() -> None:
    _failed_logins.pop(_throttle_key(), None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone") or "").strip()
    password = str(data.get("password") or "")
    if not phone or not password:
        raise ApiError("Phone and password are required.", 400, "missing_credentials")

    _check_throttle()
    row = query_one("SELECT * FROM users WHERE phone = ?", (phone,))
    if row is None or not check_password_hash(row["password_hash"], password):
        _record_failure()
        raise ApiError("Invalid credentials.", 401, "invalid_credentials")
    if not row["is_active"]:
        raise ApiError("This account has been deactivated.", 403, "account_inactive")

    _clear_failures()
    session.clear()
    session["user_id"] = row["user_id"]
    session.permanent = True
    return jsonify({"user": serialize_user(row)})


@bp.post("/logout")
def logout():
    session.clear()
    return ("", 204)


@bp.get("/me")
@login_required
def me():
    return jsonify({"user": serialize_user(g.current_user)})


@bp.post("/password")
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    user = g.current_user

    current = str(data.get("current_password") or "")
    if not check_password_hash(user["password_hash"], current):
        raise ApiError("Current password is incorrect.", 400, "wrong_password")

    new_password = validate_password(data.get("new_password"), "new_password")
    if check_password_hash(user["password_hash"], new_password):
        raise ApiError("New password must differ from the current one.", 400, "same_password")

    execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE user_id = ?",
        (generate_password_hash(new_password), user["user_id"]),
    )
    return ("", 204)
