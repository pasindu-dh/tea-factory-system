"""User management.

Owner: full CRUD over every role.
Supervisor: may register and edit servants only.
Any user: may read and lightly edit their own profile (name/phone).
Passwords never appear in responses.
"""
from __future__ import annotations

import secrets

from flask import Blueprint, g, jsonify, request
from werkzeug.security import generate_password_hash

from auth import login_required, require_role
from config import AREAS, GENDERS, ROLES, WORK_TYPES
from db import execute, query_all, query_one
from helpers import (
    ApiError,
    parse_choice,
    parse_phone,
    require_str,
    serialize_user,
    validate_password,
)

bp = Blueprint("users", __name__, url_prefix="/api/users")


def _get_or_404(user_id: int):
    row = query_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if row is None:
        raise ApiError("User not found.", 404, "not_found")
    return row


def _guard_last_owner(row, action: str) -> None:
    """Refuse to delete/deactivate/demote the only remaining active owner."""
    if row["role"] != "owner":
        return
    active_owners = query_one(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'owner' AND is_active = 1"
    )["n"]
    if active_owners <= 1:
        raise ApiError(
            f"Cannot {action} the only active owner account.",
            409,
            "last_owner",
        )


def _phone_conflict(phone: str, exclude_id: int | None = None) -> bool:
    if exclude_id is None:
        return query_one("SELECT 1 FROM users WHERE phone = ?", (phone,)) is not None
    return (
        query_one("SELECT 1 FROM users WHERE phone = ? AND user_id <> ?", (phone, exclude_id))
        is not None
    )


# ---------------------------------------------------------------------------
@bp.get("")
@require_role("owner", "supervisor")
def list_users():
    viewer = g.current_user
    where, params = [], []

    if viewer["role"] == "supervisor":
        where.append("role = 'servant'")

    role_filter = request.args.get("role")
    if role_filter:
        role_filter = parse_choice(role_filter, ROLES, "role")
        where.append("role = ?")
        params.append(role_filter)

    active_param = request.args.get("active")
    if active_param is not None:
        active = active_param.lower() in ("1", "true", "yes")
        where.append("is_active = ?")
        params.append(1 if active else 0)

    sql = "SELECT * FROM users"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY role, name"

    return jsonify({"users": [serialize_user(r) for r in query_all(sql, params)]})


@bp.post("")
@require_role("owner", "supervisor")
def create_user():
    viewer = g.current_user
    data = request.get_json(silent=True) or {}

    role = parse_choice(data.get("role"), ROLES, "role")
    if viewer["role"] == "supervisor" and role != "servant":
        raise ApiError("Supervisors can only register servants.", 403, "forbidden")

    name = require_str(data, "name")
    gender = parse_choice(data.get("gender"), GENDERS, "gender")
    phone = parse_phone(data.get("phone"))
    password = validate_password(data.get("password"))

    work_type = None
    area = None
    if role == "servant":
        work_type = parse_choice(data.get("work_type"), WORK_TYPES, "work_type")
    elif data.get("area"):
        area = parse_choice(data["area"], AREAS, "area")

    if _phone_conflict(phone):
        raise ApiError("A user with this phone number already exists.", 409, "duplicate_phone")

    cur = execute(
        """INSERT INTO users (name, role, gender, phone, password_hash, work_type, area)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, role, gender, phone, generate_password_hash(password), work_type, area),
    )
    row = query_one("SELECT * FROM users WHERE user_id = ?", (cur.lastrowid,))
    return jsonify({"user": serialize_user(row)}), 201


@bp.get("/<int:user_id>")
@login_required
def get_user(user_id: int):
    viewer = g.current_user
    row = _get_or_404(user_id)

    allowed = (
        viewer["role"] == "owner"
        or viewer["user_id"] == user_id
        or (viewer["role"] == "supervisor" and row["role"] == "servant")
    )
    if not allowed:
        raise ApiError("You do not have permission to view this user.", 403, "forbidden")
    return jsonify({"user": serialize_user(row)})


@bp.put("/<int:user_id>")
@login_required
def update_user(user_id: int):
    viewer = g.current_user
    row = _get_or_404(user_id)
    data = request.get_json(silent=True) or {}

    is_self = viewer["user_id"] == user_id
    is_owner = viewer["role"] == "owner"
    is_supervisor_of_servant = viewer["role"] == "supervisor" and row["role"] == "servant"

    if not (is_owner or is_supervisor_of_servant or is_self):
        raise ApiError("You do not have permission to edit this user.", 403, "forbidden")

    self_service_only = is_self and not is_owner

    fields: dict[str, object] = {}

    if self_service_only:
        restricted = {"role", "work_type", "gender", "area", "is_active", "password"}
        if restricted & set(data):
            raise ApiError(
                "You can only change your own name and phone number here.",
                403,
                "forbidden",
            )

    if "name" in data:
        fields["name"] = require_str(data, "name")

    if "phone" in data:
        phone = parse_phone(data["phone"])
        if _phone_conflict(phone, exclude_id=user_id):
            raise ApiError("A user with this phone number already exists.", 409, "duplicate_phone")
        fields["phone"] = phone

    if not self_service_only:
        if "gender" in data:
            fields["gender"] = parse_choice(data["gender"], GENDERS, "gender")

        new_role = row["role"]
        if "role" in data and data["role"] != row["role"]:
            if not is_owner:
                raise ApiError("Only the owner can change roles.", 403, "forbidden")
            new_role = parse_choice(data["role"], ROLES, "role")
            if row["role"] == "owner":
                _guard_last_owner(row, "change the role of")
            fields["role"] = new_role

        if new_role == "servant":
            work_value = data.get("work_type", row["work_type"])
            fields["work_type"] = parse_choice(work_value, WORK_TYPES, "work_type")
            fields["area"] = None
        else:
            fields["work_type"] = None
            if "area" in data:
                fields["area"] = parse_choice(data["area"], AREAS, "area") if data["area"] else None

        if "password" in data and str(data["password"]).strip():
            fields["password_hash"] = generate_password_hash(
                validate_password(data["password"])
            )

        if "is_active" in data:
            if not is_owner:
                raise ApiError("Only the owner can activate or deactivate accounts.", 403, "forbidden")
            active = bool(data["is_active"])
            if not active and row["role"] == "owner":
                _guard_last_owner(row, "deactivate")
            fields["is_active"] = 1 if active else 0

    if not fields:
        raise ApiError("No changes supplied.", 400, "no_changes")

    assignments = ", ".join(f"{column} = ?" for column in fields)
    execute(
        f"UPDATE users SET {assignments} WHERE user_id = ?",
        (*fields.values(), user_id),
    )
    return jsonify({"user": serialize_user(_get_or_404(user_id))})


@bp.delete("/<int:user_id>")
@require_role("owner")
def delete_user(user_id: int):
    if user_id == g.current_user["user_id"]:
        raise ApiError("You cannot delete your own account.", 409, "self_delete")

    row = _get_or_404(user_id)
    _guard_last_owner(row, "delete")

    if query_one("SELECT 1 FROM salaries WHERE servant_id = ? LIMIT 1", (user_id,)):
        raise ApiError(
            "This user has payroll history. Deactivate the account instead.",
            409,
            "has_payroll_history",
        )

    execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    return ("", 204)


@bp.post("/<int:user_id>/reset-password")
@require_role("owner")
def reset_password(user_id: int):
    """Generate a one-time temporary password the owner hands to the user."""
    row = _get_or_404(user_id)
    temp_password = secrets.token_urlsafe(6)
    execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1 WHERE user_id = ?",
        (generate_password_hash(temp_password), row["user_id"]),
    )
    return jsonify(
        {
            "user_id": row["user_id"],
            "temp_password": temp_password,
            "must_change_password": True,
        }
    )
