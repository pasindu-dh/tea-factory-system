"""Pure unit tests for the payroll engine — no Flask, no database."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from payroll import (
    attendance_pct,
    bracket_label,
    compute_period,
    current_cycle,
    daily_cost_series,
    daily_wage,
    gauge_payload,
    rainy_adjust,
    rate_for,
    round_half_up,
    rupees,
    suggested_next_cycle,
    validate_period,
)

RATES = {
    "above_80": 60.0,
    "between_70_80": 50.0,
    "below_70": 40.0,
    "male_daily": 2000.0,
    "female_daily": 1500.0,
}


class TestRainyAdjust:
    def test_100kg_deducts_5(self):
        assert rainy_adjust(100) == 95.0

    def test_50kg_deducts_2_5(self):
        assert rainy_adjust(50) == 47.5

    def test_rounds_half_up_to_two_places(self):
        assert rainy_adjust(0.5) == 0.48  # 0.475 -> 0.48

    def test_never_negative(self):
        assert rainy_adjust(0.01) >= 0


class TestRounding:
    def test_rupees_half_up_not_bankers(self):
        assert rupees(2.5) == 3  # Python's round(2.5) would give 2
        assert rupees(0.5) == 1
        assert rupees(1.49) == 1

    def test_round_half_up(self):
        assert round_half_up(2.5) == 3.0
        assert round_half_up(0.125, 2) == 0.13


class TestAttendancePct:
    @pytest.mark.parametrize(
        "present,period,expected",
        [(10, 10, 100), (8, 10, 80), (7, 10, 70), (6, 10, 60), (0, 10, 0), (0, 0, 0)],
    )
    def test_percentages(self, present, period, expected):
        assert attendance_pct(present, period) == expected

    def test_half_up_rounding(self):
        assert attendance_pct(1, 8) == 13  # 12.5% -> 13


class TestBrackets:
    @pytest.mark.parametrize(
        "pct,expected",
        [(100, 60.0), (81, 60.0), (80, 50.0), (70, 50.0), (69, 40.0), (0, 40.0)],
    )
    def test_rate_for(self, pct, expected):
        assert rate_for(pct, RATES) == expected

    def test_labels(self):
        assert bracket_label(81) == "> 80% attendance"
        assert bracket_label(80) == "70% - 80% attendance"
        assert bracket_label(69) == "< 70% attendance"

    def test_daily_wage(self):
        assert daily_wage("Male", RATES) == 2000.0
        assert daily_wage("Female", RATES) == 1500.0


class TestPeriods:
    def test_validate_period_inclusive(self):
        assert validate_period("2026-09-24", "2026-10-03") == 10
        assert validate_period("2026-09-24", "2026-09-24") == 1

    def test_reversed_period_raises(self):
        with pytest.raises(ValueError):
            validate_period("2026-10-03", "2026-09-24")

    def test_suggested_next_cycle_after_a_run(self):
        assert suggested_next_cycle("2026-09-29", "2026-10-03") == {
            "start": "2026-09-30",
            "end": "2026-10-09",
        }

    def test_suggested_next_cycle_with_no_runs(self):
        assert suggested_next_cycle(None, "2026-10-03") == {
            "start": "2026-09-24",
            "end": "2026-10-03",
        }

    def test_current_cycle_with_no_runs_is_trailing_window(self):
        cycle = current_cycle(None, "2026-10-03")
        assert cycle == {"start": "2026-09-24", "end": "2026-10-03", "day_of_cycle": 10}

    def test_current_cycle_inside_latest_run(self):
        cycle = current_cycle("2026-10-20", "2026-10-15")
        assert cycle == {"start": "2026-10-11", "end": "2026-10-20", "day_of_cycle": 5}

    def test_current_cycle_open_period_after_latest_run(self):
        cycle = current_cycle("2026-09-29", "2026-10-03")
        assert cycle == {"start": "2026-09-30", "end": "2026-10-09", "day_of_cycle": 4}

    def test_current_cycle_falls_back_when_run_is_stale(self):
        cycle = current_cycle("2026-09-19", "2026-10-03")
        assert cycle == {"start": "2026-09-24", "end": "2026-10-03", "day_of_cycle": 10}


def _days(start: str, count: int):
    start_date = date.fromisoformat(start)
    return [(start_date + timedelta(days=offset)).isoformat() for offset in range(count)]


class TestComputePeriod:
    servants = [
        {"user_id": 1, "name": "Collector", "work_type": "Tea Collector", "gender": "Male"},
        {"user_id": 2, "name": "Retailer", "work_type": "Retail Worker", "gender": "Female"},
        {"user_id": 3, "name": "Absent", "work_type": "Retail Worker", "gender": "Male"},
    ]

    def _rows(self):
        days = _days("2026-09-24", 10)
        attendance = []
        weights = []
        for day in days[:10]:
            attendance.append({"servant_id": 1, "work_date": day, "status": "Present"})
            weights.append({"servant_id": 1, "work_date": day, "adjusted_weight": 100.0})
        for day in days[:8]:
            attendance.append({"servant_id": 2, "work_date": day, "status": "Present"})
        return attendance, weights

    def test_lines_and_totals(self):
        attendance, weights = self._rows()
        result = compute_period(self.servants, attendance, weights, "2026-09-24", "2026-10-03", RATES)

        assert result["period_days"] == 10
        assert result["is_cycle"] is True

        by_id = {line["servant_id"]: line for line in result["lines"]}
        assert by_id[1]["attendance_pct"] == 100
        assert by_id[1]["total_salary"] == 60000  # 1000 kg x Rs.60
        assert by_id[2]["attendance_pct"] == 80
        assert by_id[2]["total_salary"] == 12000  # 8 days x Rs.1500 (female)
        assert by_id[3]["total_salary"] == 0

        assert result["totals"]["total_weight"] == 1000.0
        assert result["totals"]["total_salary"] == 72000

    def test_rows_outside_period_are_ignored(self):
        attendance, weights = self._rows()
        attendance.append({"servant_id": 1, "work_date": "2026-08-01", "status": "Present"})
        weights.append({"servant_id": 1, "work_date": "2026-08-01", "adjusted_weight": 9999.0})
        result = compute_period(self.servants, attendance, weights, "2026-09-24", "2026-10-03", RATES)
        by_id = {line["servant_id"]: line for line in result["lines"]}
        assert by_id[1]["total_weight"] == 1000.0

    def test_non_cycle_period_reports_days(self):
        result = compute_period(self.servants, [], [], "2026-09-24", "2026-09-28", RATES)
        assert result["period_days"] == 5
        assert result["is_cycle"] is False


class TestDailyCostSeries:
    def test_costs_sum_to_period_total(self):
        days = _days("2026-09-24", 10)
        servants = [
            {"user_id": 1, "name": "Collector", "work_type": "Tea Collector", "gender": "Male"},
            {"user_id": 2, "name": "Retailer", "work_type": "Retail Worker", "gender": "Female"},
        ]
        attendance = [{"servant_id": 1, "work_date": d, "status": "Present"} for d in days]
        attendance += [{"servant_id": 2, "work_date": d, "status": "Present"} for d in days[:8]]
        weights = [{"servant_id": 1, "work_date": d, "adjusted_weight": 100.0} for d in days]

        period = compute_period(servants, attendance, weights, "2026-09-24", "2026-10-03", RATES)
        series = daily_cost_series(period["lines"], servants, attendance, weights, "2026-09-24", "2026-10-03")

        assert len(series) == 10
        total = sum(row["cost_rs"] for row in series)
        assert abs(total - period["totals"]["total_salary"]) <= 10  # per-day rounding tolerance
        assert all(row["harvest_kg"] == 100.0 for row in series)


class TestGauge:
    def test_collector_gauge(self):
        cycle = {"start": "2026-09-24", "end": "2026-10-03", "day_of_cycle": 4}
        servant = {"user_id": 1, "name": "C", "work_type": "Tea Collector", "gender": "Male"}
        days = _days("2026-09-24", 4)
        attendance = [{"servant_id": 1, "work_date": d, "status": "Present"} for d in days]
        weights = [{"servant_id": 1, "work_date": d, "adjusted_weight": 100.0} for d in days]

        gauge = gauge_payload(servant, cycle, attendance, weights, RATES, "2026-09-27")

        assert gauge["elapsed_days"] == 4
        assert gauge["attendance_pct"] == 100
        assert gauge["earned_to_date"] == 24000  # 400 kg x 60
        assert gauge["projected_total"] == 60000
        assert gauge["progress_pct"] == 40

    def test_retail_gauge(self):
        cycle = {"start": "2026-09-24", "end": "2026-10-03", "day_of_cycle": 4}
        servant = {"user_id": 2, "name": "R", "work_type": "Retail Worker", "gender": "Female"}
        days = _days("2026-09-24", 4)
        attendance = [{"servant_id": 2, "work_date": d, "status": "Present"} for d in days]

        gauge = gauge_payload(servant, cycle, attendance, [], RATES, "2026-09-27")

        assert gauge["earned_to_date"] == 6000  # 4 x 1500
        assert gauge["projected_total"] == 15000
        assert gauge["progress_pct"] == 40
        assert gauge["rate_unit"] == "day"

    def test_gauge_handles_no_data(self):
        cycle = {"start": "2026-09-24", "end": "2026-10-03", "day_of_cycle": 1}
        servant = {"user_id": 1, "name": "C", "work_type": "Tea Collector", "gender": "Male"}
        gauge = gauge_payload(servant, cycle, [], [], RATES, "2026-09-24")
        assert gauge["earned_to_date"] == 0
        assert gauge["projected_total"] == 0
        assert gauge["progress_pct"] == 0
