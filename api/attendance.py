"""Daily attendance timecards.

Status is always derived server-side: a servant is Present iff a check-in time
exists, exactly as the original app behaved.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import require_role
from db import execute, query_all, query_one
from helpers import ApiError, parse_iso_date, parse_time, reject_future
from payroll import attendance_pct, validate_period

bp = Blueprint("attendance", __name__, url_prefix="/api/attendance")


def _servant_or_404(servant_id: int):
    row = query_one(
        "SELECT * FROM users WHERE user_id = ? AND role = 'servant'", (servant_id,)
    )
    if row is None:
        raise ApiError("Servant not found.", 404, "not_found")
    return row


def _validate_times(check_in, check_out) -> None:
    if check_in and check_out and check_out < check_in:
        raise ApiError(
            "Check-out time cannot be earlier than check-in time.",
            422,
            "invalid_time_order",
        )


def _upsert(servant_id: int, day: str, check_in, check_out, actor_id: int):
    _validate_times(check_in, check_out)
    status = "Present" if check_in else "Absent"
    existing = query_one(
        "SELECT attendance_id FROM attendance WHERE servant_id = ? AND work_date = ?",
        (servant_id, day),
    )
    if existing:
        execute(
            """UPDATE attendance
                  SET check_in = ?, check_out = ?, status = ?, recorded_by = ?,
                      updated_at = datetime('now')
                WHERE attendance_id = ?""",
            (check_in, check_out, status, actor_id, existing["attendance_id"]),
        )
        return existing["attendance_id"], status
    cur = execute(
        """INSERT INTO attendance (servant_id, work_date, check_in, check_out, status, recorded_by)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (servant_id, day, check_in, check_out, status, actor_id),
    )
    return cur.lastrowid, status


# ---------------------------------------------------------------------------
@bp.get("")
@require_role("owner", "supervisor")
def attendance_sheet():
    """One row per active servant for a day, with any existing record merged in."""
    day = parse_iso_date(request.args.get("date"), "date")
    servants = query_all(
        "SELECT * FROM users WHERE role = 'servant' AND is_active = 1 ORDER BY name"
    )
    records = {
        row["servant_id"]: row
        for row in query_all("SELECT * FROM attendance WHERE work_date = ?", (day,))
    }
    rows = []
    for servant in servants:
        record = records.get(servant["user_id"])
        rows.append(
            {
                "servant_id": servant["user_id"],
                "name": servant["name"],
                "gender": servant["gender"],
                "work_type": servant["work_type"],
                "attendance_id": record["attendance_id"] if record else None,
                "check_in": record["check_in"] if record else None,
                "check_out": record["check_out"] if record else None,
                "status": record["status"] if record else "Absent",
            }
        )
    return jsonify({"date": day, "rows": rows})


@bp.put("/<int:servant_id>/<date_str>")
@require_role("owner", "supervisor")
def update_attendance(servant_id: int, date_str: str):
    day = reject_future(parse_iso_date(date_str, "date"))
    servant = _servant_or_404(servant_id)
    if not servant["is_active"]:
        raise ApiError("This servant's account is deactivated.", 409, "account_inactive")

    data = request.get_json(silent=True) or {}
    check_in = parse_time(data.get("check_in"), "check_in")
    check_out = parse_time(data.get("check_out"), "check_out")

    attendance_id, status = _upsert(servant_id, day, check_in, check_out, g.current_user["user_id"])
    return jsonify(
        {
            "attendance_id": attendance_id,
            "servant_id": servant_id,
            "date": day,
            "check_in": check_in,
            "check_out": check_out,
            "status": status,
        }
    )


@bp.post("/bulk")
@require_role("owner", "supervisor")
def bulk_update():
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
        check_in = parse_time(entry.get("check_in"), "check_in")
        check_out = parse_time(entry.get("check_out"), "check_out")
        attendance_id, status = _upsert(servant_id, day, check_in, check_out, actor_id)
        results.append(
            {
                "servant_id": servant_id,
                "attendance_id": attendance_id,
                "check_in": check_in,
                "check_out": check_out,
                "status": status,
            }
        )
    return jsonify({"date": day, "rows": results})


@bp.get("/history")
@require_role("owner", "supervisor", "servant")
def history():
    viewer = g.current_user
    servant_id = request.args.get("servant_id", type=int)

    if viewer["role"] == "servant":
        if servant_id is not None and servant_id != viewer["user_id"]:
            raise ApiError("You can only view your own records.", 403, "forbidden")
        servant_id = viewer["user_id"]

    where, params = [], []
    if servant_id is not None:
        where.append("a.servant_id = ?")
        params.append(servant_id)

    start = request.args.get("start")
    end = request.args.get("end")
    if start or end:
        start = parse_iso_date(start, "start")
        end = parse_iso_date(end, "end")
        where.append("a.work_date BETWEEN ? AND ?")
        params.extend([start, end])

    sql = """SELECT a.*, u.name AS servant_name
               FROM attendance a JOIN users u ON u.user_id = a.servant_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.work_date DESC, u.name"
    return jsonify({"rows": [dict(row) for row in query_all(sql, params)]})


@bp.get("/summary")
@require_role("owner", "supervisor", "servant")
def summary():
    """The single source of truth for attendance percentages."""
    viewer = g.current_user
    start = parse_iso_date(request.args.get("start"), "start")
    end = parse_iso_date(request.args.get("end"), "end")
    period_days = validate_period(start, end)

    servant_id = request.args.get("servant_id", type=int)
    if viewer["role"] == "servant":
        if servant_id is not None and servant_id != viewer["user_id"]:
            raise ApiError("You can only view your own records.", 403, "forbidden")
        servant_id = viewer["user_id"]

    where = ["role = 'servant' AND is_active = 1"]
    params: list = []
    if servant_id is not None:
        where.append("user_id = ?")
        params.append(servant_id)
    servants = query_all(f"SELECT * FROM users WHERE {' AND '.join(where)} ORDER BY name", params)

    counts = {
        row["servant_id"]: row["present_days"]
        for row in query_all(
            """SELECT servant_id, COUNT(*) AS present_days
                 FROM attendance
                WHERE status = 'Present' AND work_date BETWEEN ? AND ?
                GROUP BY servant_id""",
            (start, end),
        )
    }

    rows = [
        {
            "servant_id": servant["user_id"],
            "name": servant["name"],
            "present_days": counts.get(servant["user_id"], 0),
            "period_days": period_days,
            "attendance_pct": attendance_pct(counts.get(servant["user_id"], 0), period_days),
        }
        for servant in servants
    ]
    return jsonify({"period_start": start, "period_end": end, "period_days": period_days, "rows": rows})
