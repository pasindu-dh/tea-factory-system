"""Pure payroll engine — the single source of truth for all salary maths.

No Flask and no database imports: every function here takes plain values and
returns plain values so it can be unit-tested in isolation and reused by API,
dashboard, and reporting code alike.

Rules implemented (must stay in sync with the factory's policy):
  * Rainy day   : adjusted = original - original / 20   (1 kg per 20 kg)
  * Collector   : adjusted kg x rate, where rate depends on attendance bracket
                  > 80%  -> above_80
                  70-80% -> between_70_80
                  < 70%  -> below_70
  * Retail      : present days x gender daily wage
  * Cycle length: 10 days
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence

from config import CYCLE_DAYS

# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------
# JS Math.round() rounds .5 away from zero; Python's round() is banker's
# rounding. Payouts must match the original app, so always go through Decimal
# with ROUND_HALF_UP instead of round().
def round_half_up(value: float, places: int = 0) -> float:
    quant = Decimal("1").scaleb(-places)
    result = Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP)
    return float(result)


def rupees(value: float) -> int:
    """Round a rupee amount to a whole rupee, half up."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_kg(value: float) -> float:
    """Round a weight to 2 decimal places, half up."""
    return round_half_up(value, 2)


# ---------------------------------------------------------------------------
# Core rules
# ---------------------------------------------------------------------------
def rainy_adjust(original_weight: float) -> float:
    """Moisture deduction: subtract 1 kg for every 20 kg of raw leaf."""
    deduction = original_weight / 20
    return round_kg(original_weight - deduction)


def attendance_pct(present_days: int, period_days: int) -> int:
    """Attendance percentage as a whole number, half up; 0 for an empty period."""
    if period_days <= 0:
        return 0
    return int(
        (Decimal(present_days) / Decimal(period_days) * Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def rate_for(pct: int, rates: Mapping[str, float]) -> float:
    """Per-kg rate for a Tea Collector's attendance bracket."""
    if pct > 80:
        return rates["above_80"]
    if pct >= 70:
        return rates["between_70_80"]
    return rates["below_70"]


def bracket_label(pct: int) -> str:
    if pct > 80:
        return "> 80% attendance"
    if pct >= 70:
        return "70% - 80% attendance"
    return "< 70% attendance"


def daily_wage(gender: str, rates: Mapping[str, float]) -> float:
    return rates["male_daily"] if gender == "Male" else rates["female_daily"]


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def to_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def validate_period(start, end) -> int:
    """Return the number of days in [start, end] inclusive."""
    start_d, end_d = to_date(start), to_date(end)
    if end_d < start_d:
        raise ValueError("period_end must not be before period_start")
    return (end_d - start_d).days + 1


def in_range(work_date, start, end) -> bool:
    if isinstance(work_date, str):
        return str(start) <= work_date <= str(end)
    return to_date(start) <= work_date <= to_date(end)


def suggested_next_cycle(latest_period_end, today) -> dict:
    """Default 10-day range for the salary-run form (owner picks; we suggest)."""
    today_d = to_date(today)
    if latest_period_end is None:
        start = today_d - timedelta(days=CYCLE_DAYS - 1)
        return {"start": start.isoformat(), "end": today_d.isoformat()}
    start = to_date(latest_period_end) + timedelta(days=1)
    end = start + timedelta(days=CYCLE_DAYS - 1)
    return {"start": start.isoformat(), "end": end.isoformat()}


def current_cycle(latest_period_end, today) -> dict:
    """The cycle the servant gauge tracks, as {start, end, day_of_cycle}.

    - No runs yet            -> trailing 10 days ending today.
    - Today inside the latest run period -> that period.
    - Otherwise              -> the open period right after the latest run;
                                if today is already past it, trailing 10 days.
    """
    today_d = to_date(today)

    if latest_period_end is None:
        start = today_d - timedelta(days=CYCLE_DAYS - 1)
        return {
            "start": start.isoformat(),
            "end": today_d.isoformat(),
            "day_of_cycle": CYCLE_DAYS,
        }

    latest_end = to_date(latest_period_end)
    if today_d <= latest_end:
        start = latest_end - timedelta(days=CYCLE_DAYS - 1)
        return {
            "start": start.isoformat(),
            "end": latest_end.isoformat(),
            "day_of_cycle": (today_d - start).days + 1,
        }

    start = latest_end + timedelta(days=1)
    end = start + timedelta(days=CYCLE_DAYS - 1)
    if today_d > end:
        start = today_d - timedelta(days=CYCLE_DAYS - 1)
        end = today_d
        day = CYCLE_DAYS
    else:
        day = (today_d - start).days + 1
    return {"start": start.isoformat(), "end": end.isoformat(), "day_of_cycle": day}


# ---------------------------------------------------------------------------
# Line / period computation
# ---------------------------------------------------------------------------
def _present_days(attendance_rows: Iterable[Mapping], servant_id: int, start, end) -> int:
    return sum(
        1
        for row in attendance_rows
        if row["servant_id"] == servant_id
        and row["status"] == "Present"
        and in_range(row["work_date"], start, end)
    )


def _total_weight(weight_rows: Iterable[Mapping], servant_id: int, start, end) -> float:
    return round_kg(
        sum(
            row["adjusted_weight"]
            for row in weight_rows
            if row["servant_id"] == servant_id and in_range(row["work_date"], start, end)
        )
    )


def compute_period(
    servants: Sequence[Mapping],
    attendance_rows,
    weight_rows,
    start,
    end,
    rates,
) -> dict:
    """Compute every servant's line for [start, end] plus totals.

    attendance_rows / weight_rows may be unfiltered; only rows inside the
    period are counted.
    """
    period_days = validate_period(start, end)
    start_s, end_s = str(to_date(start)), str(to_date(end))

    lines = []
    for servant in servants:
        sid = servant["user_id"]
        present = _present_days(attendance_rows, sid, start_s, end_s)
        pct = attendance_pct(present, period_days)

        if servant["work_type"] == "Tea Collector":
            weight = _total_weight(weight_rows, sid, start_s, end_s)
            rate = rate_for(pct, rates)
            salary = rupees(weight * rate)
            output_label = f"{weight:g} kg"
            rate_label = f"Rs. {rate:g} / kg ({bracket_label(pct)})"
        else:
            weight = 0.0
            rate = daily_wage(servant["gender"], rates)
            salary = rupees(present * rate)
            output_label = f"{present} days"
            rate_label = f"Rs. {rate:g} / day ({servant['gender']} wage)"

        lines.append(
            {
                "servant_id": sid,
                "name": servant["name"],
                "work_type": servant["work_type"],
                "gender": servant["gender"],
                "present_days": present,
                "period_days": period_days,
                "attendance_pct": pct,
                "total_weight": weight,
                "applied_rate": rate,
                "rate_label": rate_label,
                "output_label": output_label,
                "total_salary": salary,
            }
        )

    return {
        "period_start": start_s,
        "period_end": end_s,
        "period_days": period_days,
        "is_cycle": period_days == CYCLE_DAYS,
        "lines": lines,
        "totals": {
            "servants": len(lines),
            "total_weight": round_kg(sum(line["total_weight"] for line in lines)),
            "total_salary": sum(line["total_salary"] for line in lines),
        },
    }


def daily_cost_series(
    lines: Sequence[Mapping],
    servants: Sequence[Mapping],
    attendance_rows,
    weight_rows,
    start,
    end,
) -> list[dict]:
    """Attribute each servant's period salary to individual days.

    Used by the owner's report chart so the cost line reflects real payroll
    instead of a flat guess. Collectors: salary distributed by that day's share
    of adjusted weight. Retail: full daily wage on each present day.
    """
    start_s, end_s = str(to_date(start)), str(to_date(end))
    servant_by_id = {s["user_id"]: s for s in servants}
    start_d = to_date(start)
    days = (to_date(end) - start_d).days + 1

    by_date: dict[str, dict] = {}
    for offset in range(days):
        iso = (start_d + timedelta(days=offset)).isoformat()
        by_date[iso] = {"date": iso, "harvest_kg": 0.0, "cost_rs": 0.0}

    for row in weight_rows:
        if start_s <= row["work_date"] <= end_s and row["work_date"] in by_date:
            by_date[row["work_date"]]["harvest_kg"] += row["adjusted_weight"]

    for line in lines:
        servant = servant_by_id.get(line["servant_id"])
        if servant is None:
            continue
        if line["work_type"] == "Tea Collector":
            if line["total_weight"] <= 0:
                continue
            for row in weight_rows:
                if row["servant_id"] != line["servant_id"]:
                    continue
                if not (start_s <= row["work_date"] <= end_s):
                    continue
                share = row["adjusted_weight"] / line["total_weight"]
                by_date[row["work_date"]]["cost_rs"] += line["total_salary"] * share
        else:
            for row in attendance_rows:
                if row["servant_id"] != line["servant_id"]:
                    continue
                if row["status"] != "Present" or not (start_s <= row["work_date"] <= end_s):
                    continue
                by_date[row["work_date"]]["cost_rs"] += line["applied_rate"]

    series = []
    for iso in sorted(by_date):
        entry = by_date[iso]
        entry["harvest_kg"] = round_kg(entry["harvest_kg"])
        entry["cost_rs"] = rupees(entry["cost_rs"])
        series.append(entry)
    return series


# ---------------------------------------------------------------------------
# Servant gauge
# ---------------------------------------------------------------------------
def gauge_payload(
    servant: Mapping,
    cycle: Mapping,
    attendance_rows,
    weight_rows,
    rates,
    today,
) -> dict:
    """Live 'estimated pay so far / projected' data for the servant dashboard."""
    today_d = to_date(today)
    start, end = cycle["start"], cycle["end"]
    start_d, end_d = to_date(start), to_date(end)
    cycle_days = (end_d - start_d).days + 1

    elapsed = (today_d - start_d).days + 1
    elapsed = max(0, min(elapsed, cycle_days))
    day_of_cycle = max(1, min(int(cycle.get("day_of_cycle", elapsed)), cycle_days))

    present = _present_days(attendance_rows, servant["user_id"], start, end)
    pct = attendance_pct(present, elapsed)

    if servant["work_type"] == "Tea Collector":
        weight = _total_weight(weight_rows, servant["user_id"], start, end)
        rate = rate_for(pct, rates)
        earned = rupees(weight * rate)
        per_day = weight / elapsed if elapsed > 0 else 0.0
        projected = rupees(per_day * cycle_days * rate)
        output_total = weight
        output_unit = "kg"
    else:
        rate = daily_wage(servant["gender"], rates)
        earned = rupees(present * rate)
        projected = rupees(cycle_days * rate)
        output_total = float(present)
        output_unit = "days"

    progress = rupees(earned / projected * 100) if projected > 0 else 0
    return {
        "earned_to_date": earned,
        "projected_total": projected,
        "progress_pct": max(0, min(progress, 100)),
        "bracket": bracket_label(pct),
        "attendance_pct": pct,
        "rate": rate,
        "rate_unit": "kg" if servant["work_type"] == "Tea Collector" else "day",
        "present_days": present,
        "elapsed_days": elapsed,
        "cycle_days": cycle_days,
        "day_of_cycle": day_of_cycle,
        "cycle_start": start,
        "cycle_end": end,
        "output_total": output_total,
        "output_unit": output_unit,
    }
