"""Role-aware dashboard payloads plus the system config endpoint."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, g, jsonify, request

from api.data import attendance_rows, latest_period_end, period_days, servants, weight_rows
from api.rates import get_rates
from auth import login_required, require_role
from config import AREAS, CYCLE_DAYS, PAYMENT_METHODS, WORK_TYPES
from db import query_all, query_one
from helpers import parse_iso_date
from payroll import (
    attendance_pct,
    compute_period,
    current_cycle,
    daily_cost_series,
    gauge_payload,
    round_kg,
    suggested_next_cycle,
)

bp = Blueprint("dashboard", __name__, url_prefix="/api")


def _default_range():
    latest = latest_period_end()
    cycle = current_cycle(latest, date.today())
    return cycle["start"], cycle["end"]


def _range_from_args():
    start = request.args.get("start")
    end = request.args.get("end")
    if start or end:
        start = parse_iso_date(start, "start")
        end = parse_iso_date(end, "end")
        return start, end
    return _default_range()


@bp.get("/config")
@login_required
def system_config():
    today = date.today().isoformat()
    latest = latest_period_end()
    return jsonify(
        {
            "today": today,
            "cycle_days": CYCLE_DAYS,
            "current_cycle": current_cycle(latest, today),
            "suggested_next_cycle": suggested_next_cycle(latest, today),
            "areas": list(AREAS),
            "work_types": list(WORK_TYPES),
            "payment_methods": list(PAYMENT_METHODS),
        }
    )


def _owner_payload(start: str, end: str) -> dict:
    days = period_days(start, end)
    rates = get_rates()
    servant_rows = servants()
    att_rows = attendance_rows()
    wt_rows = weight_rows()

    period = compute_period(servant_rows, att_rows, wt_rows, start, end, rates)
    series = daily_cost_series(period["lines"], servant_rows, att_rows, wt_rows, start, end)

    today = date.today().isoformat()
    present_today = sum(
        1 for row in att_rows if row["work_date"] == today and row["status"] == "Present"
    )

    in_range = [row for row in wt_rows if start <= row["work_date"] <= end]
    rainy_rows = [row for row in in_range if row["rainy_day"]]
    rainy_deduction = round_kg(
        sum(row["original_weight"] - row["adjusted_weight"] for row in rainy_rows)
    )

    area_totals: dict[str, float] = {area: 0.0 for area in AREAS}
    for row in in_range:
        if row["area"] in area_totals:
            area_totals[row["area"]] += row["adjusted_weight"]

    supervisors = query_one(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'supervisor' AND is_active = 1"
    )["n"]

    return {
        "role": "owner",
        "period": {"start": start, "end": end, "days": days},
        "stats": {
            "servants": len(servant_rows),
            "collectors": sum(1 for s in servant_rows if s["work_type"] == "Tea Collector"),
            "retail_workers": sum(1 for s in servant_rows if s["work_type"] == "Retail Worker"),
            "supervisors": supervisors,
            "present_today": present_today,
            "absent_today": len(servant_rows) - present_today,
            "harvest_kg": period["totals"]["total_weight"],
            "estimated_payroll": period["totals"]["total_salary"],
            "rainy_deduction_kg": rainy_deduction,
        },
        "series": series,
        "area_distribution": [
            {"area": area, "kg": round_kg(kg)} for area, kg in area_totals.items()
        ],
    }


def _servant_payload(user: dict, start: str, end: str) -> dict:
    days = period_days(start, end)
    rates = get_rates()
    att_rows = attendance_rows()
    wt_rows = weight_rows()
    today = date.today().isoformat()

    latest = latest_period_end()
    cycle = current_cycle(latest, today)
    gauge = gauge_payload(user, cycle, att_rows, wt_rows, rates, today)

    my_weights = [
        row
        for row in wt_rows
        if row["servant_id"] == user["user_id"] and start <= row["work_date"] <= end
    ]
    by_date: dict[str, float] = {}
    for row in my_weights:
        by_date[row["work_date"]] = by_date.get(row["work_date"], 0.0) + row["adjusted_weight"]
    series = [
        {"date": day, "kg": round_kg(by_date[day])} for day in sorted(by_date)
    ]

    present = sum(
        1
        for row in att_rows
        if row["servant_id"] == user["user_id"]
        and row["status"] == "Present"
        and start <= row["work_date"] <= end
    )

    return {
        "role": "servant",
        "period": {"start": start, "end": end, "days": days},
        "gauge": gauge,
        "rates": rates,
        "series": series,
        "stats": {
            "total_weight": round_kg(sum(row["adjusted_weight"] for row in my_weights)),
            "present_days": present,
            "period_days": days,
            "attendance_pct": attendance_pct(present, days),
            "rate": gauge["rate"],
            "rate_unit": gauge["rate_unit"],
        },
    }


@bp.get("/dashboard")
@login_required
def dashboard():
    user = g.current_user
    start, end = _range_from_args()

    if user["role"] == "servant":
        payload = _servant_payload(user, start, end)
    else:
        payload = _owner_payload(start, end)
        payload["role"] = user["role"]

    latest = latest_period_end()
    payload["cycle"] = current_cycle(latest, date.today())
    payload["today"] = date.today().isoformat()
    return jsonify(payload)


@bp.get("/servant/records")
@require_role("servant")
def servant_records():
    user = g.current_user
    today = date.today().isoformat()

    weights = query_all(
        """SELECT w.*, u.name AS servant_name
             FROM weights w JOIN users u ON u.user_id = w.servant_id
            WHERE w.servant_id = ?
            ORDER BY w.work_date DESC, w.weight_id DESC
            LIMIT 100""",
        (user["user_id"],),
    )
    attendance = query_all(
        """SELECT * FROM attendance WHERE servant_id = ?
            ORDER BY work_date DESC LIMIT 60""",
        (user["user_id"],),
    )
    salaries = query_all(
        """SELECT s.*, r.period_start, r.period_end
             FROM salaries s JOIN payroll_runs r ON r.run_id = s.run_id
            WHERE s.servant_id = ?
            ORDER BY r.period_end DESC LIMIT 12""",
        (user["user_id"],),
    )

    latest = latest_period_end()
    cycle = current_cycle(latest, today)
    gauge = gauge_payload(user, cycle, attendance_rows(), weight_rows(), get_rates(), today)

    return jsonify(
        {
            "weights": [dict(row) for row in weights],
            "attendance": [dict(row) for row in attendance],
            "history": [
                {
                    "salary_id": row["salary_id"],
                    "period_start": row["period_start"],
                    "period_end": row["period_end"],
                    "present_days": row["present_days"],
                    "period_days": row["period_days"],
                    "attendance_pct": row["attendance_pct"],
                    "total_weight": row["total_weight"],
                    "total_salary": row["total_salary"],
                    "status": row["status"],
                    "paid_at": row["paid_at"],
                }
                for row in salaries
            ],
            "gauge": gauge,
        }
    )
