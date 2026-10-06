"""Deterministic demo data.

Seeds two cycles relative to the real current date:
  * the previous, fully completed 10-day cycle, including a finalized and fully
    paid payroll run (so payslips and salary history are demonstrable at once);
  * the current cycle up to today, so dashboards and the servant gauge are live.

All values are generated from per-record seeded RNGs, so re-running the seeder
on the same date produces identical data.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from config import DEFAULT_RATES
from db import execute, query_all
from payroll import CYCLE_DAYS, compute_period, rainy_adjust, round_kg

# user_id, name, role, gender, phone, password, work_type, area
SEED_USERS = [
    (101, "Aruna Perera", "owner", "Male", "0771112222", "owner123", None, None),
    (201, "Kamal Silva", "supervisor", "Male", "0773334444", "super123", None, "Tea Field A"),
    (202, "Nimali Fernando", "supervisor", "Female", "0775556666", "super123", None, "Factory Processing"),
    (301, "Kusal Mendis", "servant", "Male", "0777778888", "servant123", "Tea Collector", None),
    (302, "Anura Bandaranaike", "servant", "Male", "0779990000", "servant123", "Tea Collector", None),
    (303, "Pathum Nissanka", "servant", "Male", "0772223333", "servant123", "Retail Worker", None),
    (304, "Chamari Athapaththu", "servant", "Female", "0774445555", "servant123", "Retail Worker", None),
]

SERVANTS = [
    {"user_id": uid, "work_type": work_type}
    for uid, _n, role, _g, _p, _pw, work_type, _a in SEED_USERS
    if role == "servant"
]

# Which cycle-day offsets (0-9) each servant misses.
ABSENCES = {
    301: {5},          # 9/10  -> >80% bracket
    302: {1, 5, 8},    # 7/10  -> 70-80% bracket
    303: {4, 9},       # 8/10  (retail)
    304: set(),        # 10/10 (retail)
}

WEIGHT_BANDS = {301: (52.0, 88.0), 302: (40.0, 72.0)}
RAINY_OFFSETS = {2, 7}
COLLECTOR_AREAS = ("Tea Field A", "Tea Field B")
RETAIL_AREAS = ("Factory Processing", "Packaging Section")

SUPERVISOR_ID = 201
OWNER_ID = 101


def _rng(*parts) -> random.Random:
    return random.Random("|".join(str(part) for part in parts))


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _clear() -> None:
    for table in (
        "salaries",
        "payroll_runs",
        "work_area_assignments",
        "weights",
        "attendance",
        "rate_config",
        "users",
    ):
        execute(f"DELETE FROM {table}")


def _seed_users(anchor: date) -> int:
    created_at = f"{anchor.isoformat()} 08:00:00"
    for uid, name, role, gender, phone, password, work_type, area in SEED_USERS:
        execute(
            """INSERT INTO users
                   (user_id, name, role, gender, phone, password_hash, work_type, area, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid, name, role, gender, phone,
                generate_password_hash(password), work_type, area, created_at,
            ),
        )
    return len(SEED_USERS)


def _seed_rates(anchor: date) -> None:
    execute(
        """INSERT INTO rate_config
               (id, above_80, between_70_80, below_70, male_daily, female_daily, updated_at)
           VALUES (1, ?, ?, ?, ?, ?, ?)""",
        (
            DEFAULT_RATES["above_80"],
            DEFAULT_RATES["between_70_80"],
            DEFAULT_RATES["below_70"],
            DEFAULT_RATES["male_daily"],
            DEFAULT_RATES["female_daily"],
            f"{anchor.isoformat()} 08:00:00",
        ),
    )


def _seed_cycle(start: date, through: date) -> None:
    """Seed attendance, area assignments, and weights for a 10-day cycle."""
    for offset in range(CYCLE_DAYS):
        day = start + timedelta(days=offset)
        if day > through:
            break
        iso = day.isoformat()

        for servant in SERVANTS:
            sid = servant["user_id"]
            is_collector = servant["work_type"] == "Tea Collector"
            present = offset not in ABSENCES.get(sid, set())

            if present:
                rng = _rng("time", sid, iso)
                check_in = _hhmm(rng.randint(7 * 60 + 15, 8 * 60 + 5))
                check_out = _hhmm(rng.randint(16 * 60 + 40, 17 * 60 + 20))
            else:
                check_in = check_out = None

            execute(
                """INSERT INTO attendance
                       (servant_id, work_date, check_in, check_out, status, recorded_by, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid, iso, check_in, check_out,
                    "Present" if present else "Absent", SUPERVISOR_ID,
                    f"{iso} 17:30:00",
                ),
            )

            area = _rng("area", sid, iso).choice(
                COLLECTOR_AREAS if is_collector else RETAIL_AREAS
            )
            execute(
                """INSERT INTO work_area_assignments
                       (servant_id, work_date, area, assigned_by, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (sid, iso, area, SUPERVISOR_ID, f"{iso} 07:00:00"),
            )

            if is_collector and present:
                low, high = WEIGHT_BANDS[sid]
                original = round_kg(low + _rng("weight", sid, iso).random() * (high - low))
                is_rainy = offset in RAINY_OFFSETS
                adjusted = rainy_adjust(original) if is_rainy else original
                execute(
                    """INSERT INTO weights
                           (servant_id, work_date, original_weight, adjusted_weight,
                            rainy_day, area, recorded_by, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sid, iso, original, adjusted,
                        1 if is_rainy else 0, area, SUPERVISOR_ID,
                        f"{iso} 17:30:00",
                    ),
                )


def _seed_payroll_run(start: date, end: date) -> int:
    """Compile, finalize, and pay the run for a completed cycle."""
    servants = [dict(row) for row in query_all("SELECT * FROM users WHERE role = 'servant'")]
    attendance = [
        dict(row)
        for row in query_all("SELECT servant_id, work_date, status FROM attendance")
    ]
    weights = [
        dict(row)
        for row in query_all(
            "SELECT servant_id, work_date, adjusted_weight FROM weights"
        )
    ]
    period = compute_period(servants, attendance, weights, start, end, DEFAULT_RATES)

    compiled_at = f"{end.isoformat()} 18:00:00"
    finalized_at = f"{(end + timedelta(days=1)).isoformat()} 08:00:00"
    paid_at = f"{(end + timedelta(days=1)).isoformat()} 09:30:00"

    cur = execute(
        """INSERT INTO payroll_runs
               (period_start, period_end, period_days, status, rates_json,
                compiled_by, compiled_at, finalized_at)
           VALUES (?, ?, ?, 'finalized', ?, ?, ?, ?)""",
        (
            start.isoformat(),
            end.isoformat(),
            CYCLE_DAYS,
            json.dumps(DEFAULT_RATES),
            OWNER_ID,
            compiled_at,
            finalized_at,
        ),
    )
    run_id = cur.lastrowid

    for line in period["lines"]:
        execute(
            """INSERT INTO salaries
                   (run_id, servant_id, work_type, present_days, period_days,
                    attendance_pct, total_weight, applied_rate, rate_label,
                    total_salary, status, paid_at, paid_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Paid', ?, ?)""",
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
                paid_at,
                OWNER_ID,
            ),
        )
    return len(period["lines"])


def _count(table: str) -> int:
    return query_all(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


def seed_database(today: date | None = None) -> dict:
    """Wipe and reseed all demo data. Requires a Flask app context."""
    today = today or date.today()

    _clear()
    users = _seed_users(today)
    _seed_rates(today)

    # Previous completed cycle: ends 4 days ago, so the current cycle is already
    # underway the first time someone logs in.
    previous_end = today - timedelta(days=4)
    previous_start = previous_end - timedelta(days=CYCLE_DAYS - 1)
    _seed_cycle(previous_start, through=previous_end)
    salary_lines = _seed_payroll_run(previous_start, previous_end)

    # Current cycle: up to today only.
    current_start = previous_end + timedelta(days=1)
    _seed_cycle(current_start, through=today)

    return {
        "users": users,
        "attendance": _count("attendance"),
        "weights": _count("weights"),
        "assignments": _count("work_area_assignments"),
        "payroll_runs": _count("payroll_runs"),
        "salary_lines": salary_lines,
    }
