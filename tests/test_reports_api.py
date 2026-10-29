"""Owner analytics: real payroll cost in the overview, and the leaderboard."""
from __future__ import annotations

from conftest import PERIOD_END, PERIOD_START

START = PERIOD_START.isoformat()
END = PERIOD_END.isoformat()

# From the fixture: 301 -> 1000 kg, 302 -> 400 kg, 305 -> 500 dry + 95 rainy
EXPECTED_HARVEST = 1995.0
EXPECTED_PAYROLL_COST = 119800


def test_overview_totals_reflect_real_data(owner_client):
    response = owner_client.get(f"/api/reports/overview?start={START}&end={END}")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["period"]["days"] == 10
    assert payload["totals"]["harvest_kg"] == EXPECTED_HARVEST
    assert payload["totals"]["payroll_cost"] == EXPECTED_PAYROLL_COST
    assert payload["totals"]["servants"] == 5


def test_overview_rainy_aggregates(owner_client):
    payload = owner_client.get(f"/api/reports/overview?start={START}&end={END}").get_json()
    rainy = payload["rainy"]

    assert rainy["rainy_original"] == 100.0
    assert rainy["rainy_adjusted"] == 95.0
    assert rainy["rainy_deduction"] == 5.0
    assert rainy["dry_weight"] == 1900.0


def test_overview_series_uses_real_payroll_not_a_flat_rate(owner_client):
    payload = owner_client.get(f"/api/reports/overview?start={START}&end={END}").get_json()
    series = payload["series"]
    assert len(series) == 10

    total_cost = sum(row["cost_rs"] for row in series)
    assert abs(total_cost - EXPECTED_PAYROLL_COST) <= 10  # per-day rounding tolerance

    total_harvest = sum(row["harvest_kg"] for row in series)
    assert total_harvest == EXPECTED_HARVEST

    # A flat Rs.55/kg estimate would give 1995 * 55 = 109,725 — the real engine
    # pays 119,800, so the series must not match the flat-rate figure.
    assert abs(total_cost - 109725) > 100


def test_overview_changes_when_rates_change(owner_client):
    before = owner_client.get(f"/api/reports/overview?start={START}&end={END}").get_json()

    owner_client.put(
        "/api/rates",
        json={
            "above_80": 61,
            "between_70_80": 50,
            "below_70": 40,
            "male_daily": 2000,
            "female_daily": 1500,
        },
    )
    after = owner_client.get(f"/api/reports/overview?start={START}&end={END}").get_json()

    assert after["totals"]["payroll_cost"] != before["totals"]["payroll_cost"]
    assert after["totals"]["payroll_cost"] == EXPECTED_PAYROLL_COST + 1000  # 1000 kg x +1


def test_overview_area_distribution(owner_client):
    payload = owner_client.get(f"/api/reports/overview?start={START}&end={END}").get_json()
    distribution = payload["area_distribution"]
    assert len(distribution) == 4
    assert abs(sum(row["kg"] for row in distribution) - EXPECTED_HARVEST) < 0.01


def test_leaderboard_ranking_and_attendance(owner_client):
    response = owner_client.get(f"/api/reports/leaderboard?start={START}&end={END}")
    assert response.status_code == 200
    rows = response.get_json()["rows"]

    assert [row["servant_id"] for row in rows] == [301, 305, 302]
    assert [row["rank"] for row in rows] == [1, 2, 3]

    by_id = {row["servant_id"]: row for row in rows}
    assert by_id[301]["adjusted_weight"] == 1000.0
    assert by_id[301]["attendance_pct"] == 100
    assert by_id[301]["efficiency"] == "Harvest Master"  # 100 kg/day
    assert by_id[305]["deducted"] == 5.0
    assert by_id[302]["attendance_pct"] == 80

    # Attendance here must equal the attendance summary for the same range.
    summary = owner_client.get(
        f"/api/attendance/summary?start={START}&end={END}"
    ).get_json()["rows"]
    summary_by_id = {row["servant_id"]: row for row in summary}
    for row in rows:
        assert row["attendance_pct"] == summary_by_id[row["servant_id"]]["attendance_pct"]


def test_retail_worker_leaf_counts_in_harvest_but_not_pay(owner_client, supervisor_client, make_run):
    """Retail collection is real harvest; their salary rule stays daily wage."""
    created = supervisor_client.post(
        "/api/weights",
        json={
            "servant_id": 303,  # Retail Worker, 8/10 days present
            "date": "2026-09-25",
            "original_weight": 60,
            "rainy_day": False,
            "area": "Packaging Section",
        },
    )
    assert created.status_code == 201

    overview = owner_client.get(f"/api/reports/overview?start={START}&end={END}").get_json()
    assert overview["totals"]["harvest_kg"] == EXPECTED_HARVEST + 60.0
    assert overview["totals"]["payroll_cost"] == EXPECTED_PAYROLL_COST
    assert overview["rainy"]["dry_weight"] == 1960.0
    by_area = {row["area"]: row["kg"] for row in overview["area_distribution"]}
    assert by_area["Packaging Section"] == 60.0

    leaderboard = owner_client.get(
        f"/api/reports/leaderboard?start={START}&end={END}"
    ).get_json()["rows"]
    by_id = {row["servant_id"]: row for row in leaderboard}
    assert by_id[303]["adjusted_weight"] == 60.0
    assert by_id[303]["attendance_pct"] == 80
    assert [row["servant_id"] for row in leaderboard] == [301, 305, 302, 303]

    run = make_run()
    line = next(row for row in run["lines"] if row["servant_id"] == 303)
    # The retail payroll rule is present days x daily wage; the 60 kg is
    # reporting data and must not be paid at a collector's per-kg rate.
    assert line["total_salary"] == 16000
    assert line["total_weight"] == 0.0
    assert line["work_type"] == "Retail Worker"

    collector = next(row for row in run["lines"] if row["servant_id"] == 301)
    assert collector["total_salary"] == 60000
    assert collector["total_weight"] == 1000.0


def test_reports_are_owner_only(supervisor_client, servant_client):
    for client in (supervisor_client, servant_client):
        assert client.get(f"/api/reports/overview?start={START}&end={END}").status_code == 403
        assert client.get(f"/api/reports/leaderboard?start={START}&end={END}").status_code == 403


def test_invalid_range_rejected(owner_client):
    assert owner_client.get("/api/reports/overview?start=bad&end=bad").status_code == 400
    assert owner_client.get(f"/api/reports/leaderboard?start={END}&end={START}").status_code == 400
