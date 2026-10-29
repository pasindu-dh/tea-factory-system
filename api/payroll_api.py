"""Payroll: preview, 10-day runs, payslips, CSV export, servant salary history.

Runs are compiled from the pure payroll engine; each run snapshots the rates in
force at compile time, so later rate changes never alter an existing payslip.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date

from flask import Blueprint, Response, g, jsonify, request

from api.data import attendance_rows, period_days, servants, weight_rows
from api.rates import get_rates
from auth import login_required, require_role
from config import CYCLE_DAYS, PAYMENT_METHODS
from db import execute, query_all, query_one, transaction
from helpers import ApiError, parse_choice, parse_iso_date, reject_future
from payroll import compute_period

bp = Blueprint("payroll_api", __name__, url_prefix="/api/payroll")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _output_label(line) -> str:
    if line["work_type"] == "Tea Collector":
        return f"{line['total_weight']:g} kg"
    return f"{line['present_days']} days"


def _serialize_line(row) -> dict:
    return {
        "salary_id": row["salary_id"],
        "run_id": row["run_id"],
        "servant_id": row["servant_id"],
        "name": row["name"],
        "work_type": row["work_type"],
        "present_days": row["present_days"],
        "period_days": row["period_days"],
        "attendance_pct": row["attendance_pct"],
        "total_weight": row["total_weight"],
        "applied_rate": row["applied_rate"],
        "rate_label": row["rate_label"],
        "output_label": _output_label(row),
        "total_salary": row["total_salary"],
        "status": row["status"],
        "paid_at": row["paid_at"],
        "payment_method": row["payment_method"],
        "payment_ref": row["payment_ref"],
    }


def _serialize_run(row) -> dict:
    return {
        "run_id": row["run_id"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "period_days": row["period_days"],
        "status": row["status"],
        "compiled_by": row["compiled_by"],
        "compiled_by_name": row["compiled_by_name"] if "compiled_by_name" in row.keys() else None,
        "compiled_at": row["compiled_at"],
        "finalized_at": row["finalized_at"],
        "rates": json.loads(row["rates_json"]),
        "servant_count": row["servant_count"] if "servant_count" in row.keys() else None,
        "paid_count": row["paid_count"] if "paid_count" in row.keys() else None,
        "total_salary": row["total_salary"] if "total_salary" in row.keys() else None,
    }


def _get_run_or_404(run_id: int):
    row = query_one(
        """SELECT r.*, u.name AS compiled_by_name
             FROM payroll_runs r LEFT JOIN users u ON u.user_id = r.compiled_by
            WHERE r.run_id = ?""",
        (run_id,),
    )
    if row is None:
        raise ApiError("Payroll run not found.", 404, "not_found")
    return row


def _run_lines(run_id: int) -> list[dict]:
    return [
        dict(row)
        for row in query_all(
            """SELECT s.*, u.name, u.gender
                 FROM salaries s JOIN users u ON u.user_id = s.servant_id
                WHERE s.run_id = ? ORDER BY u.name""",
            (run_id,),
        )
    ]


def _run_payload(run_id: int, servant_only_id: int | None = None) -> dict:
    run = _get_run_or_404(run_id)
    lines = _run_lines(run_id)
    if servant_only_id is not None:
        lines = [line for line in lines if line["servant_id"] == servant_only_id]
    return {
        "run": _serialize_run(run),
        "lines": [_serialize_line(line) for line in lines],
    }


def _payslip_or_404(salary_id: int):
    row = query_one(
        """SELECT s.*, u.name, u.phone, u.gender,
                  r.period_start, r.period_end, r.period_days, r.status AS run_status,
                  r.rates_json, r.compiled_at, r.finalized_at
             FROM salaries s
             JOIN payroll_runs r ON r.run_id = s.run_id
             JOIN users u ON u.user_id = s.servant_id
            WHERE s.salary_id = ?""",
        (salary_id,),
    )
    if row is None:
        raise ApiError("Payslip not found.", 404, "not_found")
    return row


def _payslip_payload(row) -> dict:
    return {
        "salary_id": row["salary_id"],
        "run_id": row["run_id"],
        "servant_id": row["servant_id"],
        "name": row["name"],
        "phone": row["phone"],
        "gender": row["gender"],
        "work_type": row["work_type"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "period_days": row["period_days"],
        "present_days": row["present_days"],
        "attendance_pct": row["attendance_pct"],
        "total_weight": row["total_weight"],
        "applied_rate": row["applied_rate"],
        "rate_label": row["rate_label"],
        "output_label": _output_label(row),
        "total_salary": row["total_salary"],
        "status": row["status"],
        "paid_at": row["paid_at"],
        "payment_method": row["payment_method"],
        "payment_ref": row["payment_ref"],
        "run_status": row["run_status"],
        "compiled_at": row["compiled_at"],
        "finalized_at": row["finalized_at"],
    }


# A spreadsheet treats a cell beginning with one of these as a formula.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Neutralise CSV/formula injection without changing ordinary values."""
    if isinstance(value, str) and value.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def _csv_response(filename: str, header: list[str], rows: list[list]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows([[_csv_safe(cell) for cell in row] for row in rows])
    return Response(
        "﻿" + buffer.getvalue(),  # BOM so Excel reads UTF-8 correctly
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Preview and runs
# ---------------------------------------------------------------------------
@bp.get("/preview")
@require_role("owner")
def preview():
    """Non-mutating payroll computation for any date range."""
    start = parse_iso_date(request.args.get("start"), "start")
    end = reject_future(parse_iso_date(request.args.get("end"), "end"), "end")
    period_days(start, end)  # reject reversed ranges with a 400

    result = compute_period(
        servants(), attendance_rows(), weight_rows(), start, end, get_rates()
    )

    existing = query_one(
        "SELECT run_id, status FROM payroll_runs WHERE period_start = ? AND period_end = ?",
        (start, end),
    )
    existing_run = None
    if existing:
        lines = [
            {
                "salary_id": line["salary_id"],
                "servant_id": line["servant_id"],
                "status": line["status"],
            }
            for line in _run_lines(existing["run_id"])
        ]
        existing_run = {
            "run_id": existing["run_id"],
            "status": existing["status"],
            "lines": lines,
        }

    result["existing_run"] = existing_run
    return jsonify(result)


@bp.post("/runs")
@require_role("owner")
def create_run():
    data = request.get_json(silent=True) or {}
    start = parse_iso_date(data.get("start"), "start")
    end = parse_iso_date(data.get("end"), "end")
    days = period_days(start, end)

    if days != CYCLE_DAYS:
        raise ApiError(
            f"A payroll run must cover exactly {CYCLE_DAYS} days "
            f"(the selected range is {days}).",
            409,
            "not_a_cycle",
        )
    if date.fromisoformat(end) >= date.today():
        raise ApiError(
            "This 10-day cycle has not finished yet. Compile it on the day "
            "after its final day, once all attendance and weights are recorded.",
            422,
            "cycle_incomplete",
        )

    rates = get_rates()
    result = compute_period(
        servants(), attendance_rows(), weight_rows(), start, end, rates
    )

    with transaction():
        if query_one(
            "SELECT 1 FROM payroll_runs WHERE period_start = ? AND period_end = ?",
            (start, end),
        ):
            raise ApiError(
                "A payroll run already exists for this period.", 409, "duplicate_run"
            )
        overlap = query_one(
            """SELECT run_id, period_start, period_end FROM payroll_runs
                WHERE period_start <= ? AND period_end >= ? LIMIT 1""",
            (end, start),
        )
        if overlap:
            raise ApiError(
                "These dates overlap payroll run "
                f"#{overlap['run_id']} ({overlap['period_start']} to "
                f"{overlap['period_end']}). A day can only be paid once.",
                409,
                "overlapping_run",
            )

        cur = execute(
            """INSERT INTO payroll_runs
                   (period_start, period_end, period_days, status, rates_json, compiled_by)
               VALUES (?, ?, ?, 'draft', ?, ?)""",
            (start, end, days, json.dumps(rates), g.current_user["user_id"]),
        )
        run_id = cur.lastrowid
        for line in result["lines"]:
            execute(
                """INSERT INTO salaries
                       (run_id, servant_id, work_type, present_days, period_days,
                        attendance_pct, total_weight, applied_rate, rate_label,
                        total_salary, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')""",
                (
                    run_id,
                    line["servant_id"],
                    line["work_type"],
                    line["present_days"],
                    line["period_days"],
                    line["attendance_pct"],
                    line["total_weight"],
                    line["applied_rate"],
                    line["rate_label"],
                    line["total_salary"],
                ),
            )
    return jsonify(_run_payload(run_id)), 201


@bp.get("/runs")
@require_role("owner")
def list_runs():
    limit = min(max(request.args.get("limit", 25, type=int), 1), 100)
    rows = query_all(
        """SELECT r.*,
                  (SELECT COUNT(*) FROM salaries s WHERE s.run_id = r.run_id) AS servant_count,
                  (SELECT COUNT(*) FROM salaries s WHERE s.run_id = r.run_id AND s.status = 'Paid') AS paid_count,
                  (SELECT COALESCE(SUM(s.total_salary), 0) FROM salaries s WHERE s.run_id = r.run_id) AS total_salary
             FROM payroll_runs r
            ORDER BY r.period_end DESC, r.run_id DESC
            LIMIT ?""",
        (limit,),
    )
    return jsonify({"runs": [_serialize_run(row) for row in rows]})


@bp.get("/runs/<int:run_id>")
@login_required
def get_run(run_id: int):
    viewer = g.current_user
    if viewer["role"] == "servant":
        payload = _run_payload(run_id, servant_only_id=viewer["user_id"])
        if not payload["lines"]:
            raise ApiError("Payroll run not found.", 404, "not_found")
        return jsonify(payload)
    if viewer["role"] != "owner":
        raise ApiError("Forbidden.", 403, "forbidden")
    return jsonify(_run_payload(run_id))


@bp.delete("/runs/<int:run_id>")
@require_role("owner")
def delete_run(run_id: int):
    run = _get_run_or_404(run_id)
    if run["status"] != "draft":
        raise ApiError("Only draft runs can be deleted.", 409, "run_finalized")
    execute("DELETE FROM payroll_runs WHERE run_id = ?", (run_id,))
    return ("", 204)


@bp.post("/runs/<int:run_id>/finalize")
@require_role("owner")
def finalize_run(run_id: int):
    run = _get_run_or_404(run_id)
    if run["status"] == "finalized":
        return jsonify(_run_payload(run_id))
    execute(
        "UPDATE payroll_runs SET status = 'finalized', finalized_at = datetime('now') WHERE run_id = ?",
        (run_id,),
    )
    return jsonify(_run_payload(run_id))


@bp.post("/runs/<int:run_id>/pay")
@require_role("owner")
def pay_run(run_id: int):
    """Mark lines paid. Omit salary_ids to pay every pending line.

    `payment_method` and `payment_ref` are optional; omitting them leaves any
    already-recorded values untouched rather than clearing them.
    """
    data = request.get_json(silent=True) or {}
    requested = data.get("salary_ids")

    payment_method = data.get("payment_method")
    if payment_method is not None:
        parse_choice(payment_method, PAYMENT_METHODS, "payment_method")

    payment_ref = data.get("payment_ref")
    if payment_ref is not None:
        payment_ref = str(payment_ref).strip() or None
        if payment_ref and len(payment_ref) > 60:
            raise ApiError(
                "payment_ref must be at most 60 characters.", 400, "field_too_long"
            )

    with transaction():
        run = _get_run_or_404(run_id)
        lines = _run_lines(run_id)
        if requested is None:
            targets = [line["salary_id"] for line in lines if line["status"] == "Pending"]
        else:
            if not isinstance(requested, list):
                raise ApiError("salary_ids must be a list.", 400, "invalid_salary_ids")
            valid_ids = {line["salary_id"] for line in lines}
            unknown = [sid for sid in requested if sid not in valid_ids]
            if unknown:
                raise ApiError(
                    f"Unknown salary ids for this run: {unknown}.", 400, "invalid_salary_ids"
                )
            targets = requested

        if not targets:
            raise ApiError("There are no pending lines to pay.", 409, "nothing_to_pay")

        for salary_id in targets:
            execute(
                """UPDATE salaries
                      SET status = 'Paid', paid_at = datetime('now'), paid_by = ?,
                          payment_method = COALESCE(?, payment_method),
                          payment_ref = COALESCE(?, payment_ref)
                    WHERE salary_id = ?""",
                (g.current_user["user_id"], payment_method, payment_ref, salary_id),
            )

        if run["status"] == "draft":
            execute(
                "UPDATE payroll_runs SET status = 'finalized', finalized_at = datetime('now') WHERE run_id = ?",
                (run_id,),
            )
    return jsonify(_run_payload(run_id))


# ---------------------------------------------------------------------------
# Payslips and exports
# ---------------------------------------------------------------------------
def _payslip_access(row, viewer) -> None:
    if viewer["role"] == "owner" or viewer["user_id"] == row["servant_id"]:
        return
    raise ApiError("You do not have permission to view this payslip.", 403, "forbidden")


@bp.get("/payslips/<int:salary_id>")
@login_required
def get_payslip(salary_id: int):
    row = _payslip_or_404(salary_id)
    _payslip_access(row, g.current_user)
    return jsonify({"payslip": _payslip_payload(row)})


@bp.get("/payslips/<int:salary_id>/export")
@login_required
def export_payslip(salary_id: int):
    if request.args.get("format", "csv") != "csv":
        raise ApiError("Only format=csv is supported.", 400, "unsupported_format")
    row = _payslip_or_404(salary_id)
    _payslip_access(row, g.current_user)
    slip = _payslip_payload(row)

    filename = f"payslip_SRV-{slip['servant_id']}_{slip['period_start']}_{slip['period_end']}.csv"
    rows = [
        ["Payslip", f"SRV-{slip['servant_id']}"],
        ["Name", slip["name"]],
        ["Work type", slip["work_type"]],
        ["Period", f"{slip['period_start']} to {slip['period_end']}"],
        ["Period days", slip["period_days"]],
        ["Days present", slip["present_days"]],
        ["Attendance %", slip["attendance_pct"]],
        ["Output", slip["output_label"]],
        ["Rate", slip["rate_label"]],
        ["Gross salary (Rs.)", slip["total_salary"]],
        ["Status", slip["status"]],
        ["Paid at", slip["paid_at"] or ""],
        ["Payment method", slip["payment_method"] or ""],
        ["Payment ref", slip["payment_ref"] or ""],
    ]
    return _csv_response(filename, ["Field", "Value"], rows)


@bp.get("/runs/<int:run_id>/export")
@require_role("owner")
def export_run(run_id: int):
    if request.args.get("format", "csv") != "csv":
        raise ApiError("Only format=csv is supported.", 400, "unsupported_format")
    run = _get_run_or_404(run_id)
    lines = _run_lines(run_id)

    filename = f"payroll_run_{run['period_start']}_{run['period_end']}.csv"
    rows = [
        [
            f"SRV-{line['servant_id']}",
            line["name"],
            line["work_type"],
            line["present_days"],
            line["period_days"],
            line["attendance_pct"],
            _output_label(line),
            line["rate_label"],
            line["total_salary"],
            line["status"],
            line["paid_at"] or "",
            line["payment_method"] or "",
            line["payment_ref"] or "",
        ]
        for line in lines
    ]
    header = [
        "Servant ID",
        "Name",
        "Work type",
        "Days present",
        "Period days",
        "Attendance %",
        "Output",
        "Rate",
        "Total salary (Rs.)",
        "Status",
        "Paid at",
        "Payment method",
        "Payment ref",
    ]
    return _csv_response(filename, header, rows)


@bp.get("/my-history")
@require_role("servant")
def my_history():
    rows = query_all(
        """SELECT s.*, r.period_start, r.period_end, r.period_days, r.status AS run_status
             FROM salaries s JOIN payroll_runs r ON r.run_id = s.run_id
            WHERE s.servant_id = ?
            ORDER BY r.period_end DESC, s.salary_id DESC""",
        (g.current_user["user_id"],),
    )
    history = [
        {
            "salary_id": row["salary_id"],
            "run_id": row["run_id"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "period_days": row["period_days"],
            "present_days": row["present_days"],
            "attendance_pct": row["attendance_pct"],
            "output_label": _output_label(row),
            "rate_label": row["rate_label"],
            "total_salary": row["total_salary"],
            "status": row["status"],
            "paid_at": row["paid_at"],
        }
        for row in rows
    ]
    return jsonify({"history": history})
