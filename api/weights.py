"""Tea-leaf weighing.

The adjusted weight is always computed on the server with the rainy-day rule
(adjusted = original - original/20); any adjusted_weight sent by a client is
ignored.

Both registered work types may collect leaf. Retail workers keep their
`work_type`; the weight record does not convert them into collectors, and the
payroll engine continues to pay retail workers their daily wage rather than the
per-kg collector rate.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required, require_role
from config import AREAS
from db import execute, query_all, query_one
from helpers import ApiError, parse_choice, parse_iso_date, parse_positive_number, reject_future
from payroll import rainy_adjust, round_kg

bp = Blueprint("weights", __name__, url_prefix="/api/weights")


# A servant of either registered work type may collect leaf on a given day.
# The work type itself is never changed by weighing.
WEIGHABLE_WORK_TYPES = ("Tea Collector", "Retail Worker")


def _weighable_servant_or_404(servant_id: int):
    row = query_one(
        "SELECT * FROM users WHERE user_id = ? AND role = 'servant'", (servant_id,)
    )
    if row is None:
        # Owners and supervisors are not servants at all; a typo or a forged id
        # must never create a weight record for a staff account.
        raise ApiError("Servant not found.", 404, "not_found")
    if row["work_type"] not in WEIGHABLE_WORK_TYPES:
        raise ApiError(
            "Tea weights can only be recorded for Tea Collectors or Retail Workers.",
            422,
            "not_eligible",
        )
    if not row["is_active"]:
        raise ApiError("This servant's account is deactivated.", 409, "account_inactive")
    return row


@bp.get("")
@login_required
def list_weights():
    viewer = g.current_user
    if viewer["role"] not in ("owner", "supervisor", "servant"):
        raise ApiError("Forbidden.", 403, "forbidden")

    where, params = [], []

    if viewer["role"] == "servant":
        where.append("w.servant_id = ?")
        params.append(viewer["user_id"])
    else:
        servant_id = request.args.get("servant_id", type=int)
        if servant_id is not None:
            where.append("w.servant_id = ?")
            params.append(servant_id)

    day = request.args.get("date")
    start = request.args.get("start")
    end = request.args.get("end")
    if day:
        where.append("w.work_date = ?")
        params.append(parse_iso_date(day, "date"))
    elif start or end:
        start = parse_iso_date(start, "start")
        end = parse_iso_date(end, "end")
        where.append("w.work_date BETWEEN ? AND ?")
        params.extend([start, end])

    sql = """SELECT w.*, u.name AS servant_name, u.work_type
               FROM weights w JOIN users u ON u.user_id = w.servant_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY w.work_date DESC, w.weight_id DESC"
    return jsonify({"rows": [dict(row) for row in query_all(sql, params)]})


@bp.post("/preview")
@require_role("owner", "supervisor")
def preview():
    """Server-side rainy-day maths for the live entry preview."""
    data = request.get_json(silent=True) or {}
    original = parse_positive_number(data.get("original_weight"), "original_weight")
    rainy = bool(data.get("rainy_day"))
    adjusted = rainy_adjust(original) if rainy else round_kg(original)
    return jsonify(
        {
            "original_weight": round_kg(original),
            "rainy_day": rainy,
            "deduction": round_kg(original - adjusted),
            "adjusted_weight": adjusted,
        }
    )


@bp.post("")
@require_role("owner", "supervisor")
def create_weight():
    data = request.get_json(silent=True) or {}
    servant_id = data.get("servant_id")
    if not isinstance(servant_id, int):
        raise ApiError("servant_id is required.", 400, "missing_servant")

    _weighable_servant_or_404(servant_id)
    day = reject_future(parse_iso_date(data.get("date"), "date"))
    original = parse_positive_number(data.get("original_weight"), "original_weight")
    rainy = bool(data.get("rainy_day"))
    area = parse_choice(data.get("area"), AREAS, "area")

    adjusted = rainy_adjust(original) if rainy else round_kg(original)
    cur = execute(
        """INSERT INTO weights
               (servant_id, work_date, original_weight, adjusted_weight, rainy_day, area, recorded_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (servant_id, day, round_kg(original), adjusted, 1 if rainy else 0, area, g.current_user["user_id"]),
    )
    row = query_one(
        """SELECT w.*, u.name AS servant_name, u.work_type
             FROM weights w JOIN users u ON u.user_id = w.servant_id
            WHERE w.weight_id = ?""",
        (cur.lastrowid,),
    )
    return jsonify({"weight": dict(row)}), 201


@bp.delete("/<int:weight_id>")
@require_role("owner", "supervisor")
def delete_weight(weight_id: int):
    row = query_one("SELECT weight_id FROM weights WHERE weight_id = ?", (weight_id,))
    if row is None:
        raise ApiError("Weight record not found.", 404, "not_found")
    execute("DELETE FROM weights WHERE weight_id = ?", (weight_id,))
    return ("", 204)
