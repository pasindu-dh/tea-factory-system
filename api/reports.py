"""Owner analytics: harvest/cost overview and the productivity leaderboard.

Cost figures come from the real payroll engine (rates, brackets, weights), not
a flat estimate.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from api.data import attendance_rows, period_days, servants, weight_rows
from api.rates import get_rates
from auth import require_role
from config import AREAS
from helpers import parse_iso_date
from payroll import compute_period, daily_cost_series, round_kg

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def _range():
    start = parse_iso_date(request.args.get("start"), "start")
    end = parse_iso_date(request.args.get("end"), "end")
    return start, end


@bp.get("/overview")
@require_role("owner")
def overview():
    start, end = _range()
    days = period_days(start, end)

    rates = get_rates()
    servant_rows = servants()
    att_rows = attendance_rows()
    wt_rows = weight_rows()

    period = compute_period(servant_rows, att_rows, wt_rows, start, end, rates)
    series = daily_cost_series(period["lines"], servant_rows, att_rows, wt_rows, start, end)

    in_range = [row for row in wt_rows if start <= row["work_date"] <= end]
    dry_weight = round_kg(
        sum(row["adjusted_weight"] for row in in_range if not row["rainy_day"])
    )
    rainy_original = round_kg(
        sum(row["original_weight"] for row in in_range if row["rainy_day"])
    )
    rainy_adjusted = round_kg(
        sum(row["adjusted_weight"] for row in in_range if row["rainy_day"])
    )

    area_totals = {area: 0.0 for area in AREAS}
    for row in in_range:
        if row["area"] in area_totals:
            area_totals[row["area"]] += row["adjusted_weight"]

    return jsonify(
        {
            "period": {"start": start, "end": end, "days": days},
            "series": series,
            "rainy": {
                "dry_weight": dry_weight,
                "rainy_original": rainy_original,
                "rainy_adjusted": rainy_adjusted,
                "rainy_deduction": round_kg(rainy_original - rainy_adjusted),
            },
            "area_distribution": [
                {"area": area, "kg": round_kg(kg)} for area, kg in area_totals.items()
            ],
            "totals": {
                "servants": period["totals"]["servants"],
                "harvest_kg": period["totals"]["total_weight"],
                "payroll_cost": period["totals"]["total_salary"],
            },
        }
    )


@bp.get("/leaderboard")
@require_role("owner")
def leaderboard():
    start, end = _range()
    period_days(start, end)  # reject reversed ranges with a 400
    rates = get_rates()
    servant_rows = servants()
    att_rows = attendance_rows()
    wt_rows = weight_rows()

    period = compute_period(servant_rows, att_rows, wt_rows, start, end, rates)

    rows = []
    for line in period["lines"]:
        if line["work_type"] != "Tea Collector":
            continue
        mine = [
            row
            for row in wt_rows
            if row["servant_id"] == line["servant_id"] and start <= row["work_date"] <= end
        ]
        days_worked = len({row["work_date"] for row in mine})
        original = round_kg(sum(row["original_weight"] for row in mine))
        adjusted = round_kg(sum(row["adjusted_weight"] for row in mine))
        daily_avg = round_kg(adjusted / days_worked) if days_worked else 0.0

        if daily_avg > 60:
            efficiency = "Harvest Master"
        elif daily_avg >= 40:
            efficiency = "Consistent"
        else:
            efficiency = "Building Up"

        rows.append(
            {
                "servant_id": line["servant_id"],
                "name": line["name"],
                "attendance_pct": line["attendance_pct"],
                "days_worked": days_worked,
                "original_weight": original,
                "deducted": round_kg(original - adjusted),
                "adjusted_weight": adjusted,
                "daily_avg": daily_avg,
                "efficiency": efficiency,
            }
        )

    rows.sort(key=lambda row: row["adjusted_weight"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    return jsonify({"period": {"start": start, "end": end}, "rows": rows})
