"""Daily work-area assignment: which section each servant works in today."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import require_role
from config import AREAS
from db import execute, query_all, query_one
from helpers import ApiError, parse_choice, parse_iso_date, reject_future

bp = Blueprint("assignments", __name__, url_prefix="/api/assignments")


def _servant_or_404(servant_id: int):
    row = query_one(
        "SELECT * FROM users WHERE user_id = ? AND role = 'servant'", (servant_id,)
    )
    if row is None:
        raise ApiError("Servant not found.", 404, "not_found")
    if not row["is_active"]:
        raise ApiError("This servant's account is deactivated.", 409, "account_inactive")
    return row


def _upsert(servant_id: int, day: str, area: str, actor_id: int) -> None:
    existing = query_one(
        "SELECT assignment_id FROM work_area_assignments WHERE servant_id = ? AND work_date = ?",
        (servant_id, day),
    )
    if existing:
        execute(
            "UPDATE work_area_assignments SET area = ?, assigned_by = ? WHERE assignment_id = ?",
            (area, actor_id, existing["assignment_id"]),
        )
    else:
        execute(
            """INSERT INTO work_area_assignments (servant_id, work_date, area, assigned_by)
               VALUES (?, ?, ?, ?)""",
            (servant_id, day, area, actor_id),
        )


def _clear(servant_id: int, day: str) -> None:
    execute(
        "DELETE FROM work_area_assignments WHERE servant_id = ? AND work_date = ?",
        (servant_id, day),
    )


# ---------------------------------------------------------------------------
@bp.get("")
@require_role("owner", "supervisor")
def get_assignments():
    """Every active servant for a date, with their area (null = unassigned)."""
    day = parse_iso_date(request.args.get("date"), "date")
    servants = query_all(
        "SELECT * FROM users WHERE role = 'servant' AND is_active = 1 ORDER BY name"
    )
    assigned = {
        row["servant_id"]: row["area"]
        for row in query_all(
            "SELECT servant_id, area FROM work_area_assignments WHERE work_date = ?", (day,)
        )
    }
    rows = [
        {
            "servant_id": servant["user_id"],
            "name": servant["name"],
            "work_type": servant["work_type"],
            "area": assigned.get(servant["user_id"]),
        }
        for servant in servants
    ]
    return jsonify({"date": day, "areas": list(AREAS), "rows": rows})


@bp.put("/<int:servant_id>/<date_str>")
@require_role("owner", "supervisor")
def set_assignment(servant_id: int, date_str: str):
    day = reject_future(parse_iso_date(date_str, "date"))
    _servant_or_404(servant_id)
    data = request.get_json(silent=True) or {}
    area = parse_choice(data.get("area"), AREAS, "area")
    _upsert(servant_id, day, area, g.current_user["user_id"])
    return jsonify({"servant_id": servant_id, "date": day, "area": area})


@bp.post("/bulk")
@require_role("owner", "supervisor")
def bulk_set():
    data = request.get_json(silent=True) or {}
    day = reject_future(parse_iso_date(data.get("date"), "date"))
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ApiError("entries must be a non-empty list.", 400, "missing_entries")

    actor_id = g.current_user["user_id"]
    results = []
    for entry in entries:
        servant_id = entry.get("servant_id")
        if not isinstance(servant_id, int):
            raise ApiError("Each entry needs an integer servant_id.", 400, "invalid_servant_id")
        _servant_or_404(servant_id)
        area = entry.get("area")
        if area is None or area == "":
            _clear(servant_id, day)
            results.append({"servant_id": servant_id, "area": None})
        else:
            area = parse_choice(area, AREAS, "area")
            _upsert(servant_id, day, area, actor_id)
            results.append({"servant_id": servant_id, "area": area})
    return jsonify({"date": day, "rows": results})


@bp.delete("/<int:servant_id>/<date_str>")
@require_role("owner", "supervisor")
def delete_assignment(servant_id: int, date_str: str):
    day = parse_iso_date(date_str, "date")
    _clear(servant_id, day)
    return ("", 204)
