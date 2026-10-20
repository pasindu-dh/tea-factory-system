"""System config, the role-aware dashboard, and the servant activity ledger.

Every dashboard request passes an explicit start/end: the default range is the
*current* cycle, which moves with the wall clock and would make assertions
time-dependent. The fixture data lives in a fixed 2026-09-24 .. 2026-10-03 window.
"""
from __future__ import annotations

from datetime import date

from config import AREAS, CYCLE_DAYS, WORK_TYPES
from conftest import PERIOD_END, PERIOD_START

START = PERIOD_START.isoformat()
END = PERIOD_END.isoformat()
PERIOD = {"start": START, "end": END, "days": 10}

# From the fixture: 301 -> 1000 kg, 302 -> 400 kg, 305 -> 500 dry + 95 rainy
EXPECTED_HARVEST = 1995.0
EXPECTED_PAYROLL_COST = 119800

GAUGE_KEYS = {
    "earned_to_date",
    "projected_total",
    "progress_pct",
    "bracket",
    "attendance_pct",
    "rate",
    "rate_unit",
    "present_days",
    "elapsed_days",
    "cycle_days",
    "day_of_cycle",
    "cycle_start",
    "cycle_end",
    "output_total",
    "output_unit",
}


# ---------------------------------------------------------------------------
# GET /api/config
# ---------------------------------------------------------------------------
def test_config_exposes_domain_lists_and_today(servant_client):
    response = servant_client.get("/api/config")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["cycle_days"] == CYCLE_DAYS == 10
    assert payload["areas"] == list(AREAS)
    assert payload["work_types"] == list(WORK_TYPES)
    assert payload["today"] == date.today().isoformat()


def test_config_suggested_next_cycle_follows_the_latest_run(owner_client, make_run):
    # Before any run the suggestion is the trailing 10 days ending today.
    before = owner_client.get("/api/config").get_json()["suggested_next_cycle"]
    assert before["end"] == date.today().isoformat()
    assert before["start"] < before["end"]

    make_run()

    # Afterwards it is the 10 days immediately after the compiled period.
    after = owner_client.get("/api/config").get_json()["suggested_next_cycle"]
    assert after == {"start": "2026-10-04", "end": "2026-10-13"}


def test_config_current_cycle_is_a_ten_day_window(servant_client):
    cycle = servant_client.get("/api/config").get_json()["current_cycle"]

    span = date.fromisoformat(cycle["end"]) - date.fromisoformat(cycle["start"])
    assert span.days == CYCLE_DAYS - 1
    assert 1 <= cycle["day_of_cycle"] <= CYCLE_DAYS


def test_config_requires_login(client):
    assert client.get("/api/config").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/dashboard -- owner and supervisor (staff payload)
# ---------------------------------------------------------------------------
def test_owner_dashboard_totals_for_the_fixture_period(owner_client):
    response = owner_client.get(f"/api/dashboard?start={START}&end={END}")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["role"] == "owner"
    assert payload["period"] == PERIOD

    stats = payload["stats"]
    assert stats["servants"] == 5
    assert stats["collectors"] == 3
    assert stats["retail_workers"] == 2
    assert stats["supervisors"] == 1
    assert stats["harvest_kg"] == EXPECTED_HARVEST
    assert stats["estimated_payroll"] == EXPECTED_PAYROLL_COST
    assert stats["rainy_deduction_kg"] == 5.0

    assert len(payload["series"]) == 10


def test_owner_dashboard_series_cost_sums_to_payroll(owner_client):
    payload = owner_client.get(f"/api/dashboard?start={START}&end={END}").get_json()
    total_cost = sum(row["cost_rs"] for row in payload["series"])
    assert abs(total_cost - EXPECTED_PAYROLL_COST) <= 10  # per-day rounding tolerance

    assert sum(row["harvest_kg"] for row in payload["series"]) == EXPECTED_HARVEST


def test_owner_dashboard_area_distribution(owner_client):
    payload = owner_client.get(f"/api/dashboard?start={START}&end={END}").get_json()
    by_area = {row["area"]: row["kg"] for row in payload["area_distribution"]}

    assert set(by_area) == set(AREAS)
    assert by_area["Tea Field A"] == 1595.0  # 301 (1000) + 305 (500 dry + 95 rainy)
    assert by_area["Tea Field B"] == 400.0  # 302
    assert by_area["Factory Processing"] == 0.0
    assert by_area["Packaging Section"] == 0.0


def test_supervisor_gets_the_staff_payload_not_the_servant_one(supervisor_client):
    payload = supervisor_client.get(f"/api/dashboard?start={START}&end={END}").get_json()

    assert payload["role"] == "supervisor"
    assert payload["stats"]["servants"] == 5
    assert len(payload["series"]) == 10
    # Supervisors are staff: they must not receive the servant gauge.
    assert "gauge" not in payload


# ---------------------------------------------------------------------------
# GET /api/dashboard -- servant (own data only)
# ---------------------------------------------------------------------------
def test_servant_dashboard_uses_only_their_own_data(servant_client, servant_305_client):
    payload = servant_client.get(f"/api/dashboard?start={START}&end={END}").get_json()

    assert payload["role"] == "servant"
    assert payload["period"] == PERIOD
    assert payload["rates"]["above_80"] == 60.0

    stats = payload["stats"]
    assert stats["total_weight"] == 1000.0
    assert stats["present_days"] == 10
    assert stats["period_days"] == 10
    assert stats["attendance_pct"] == 100

    assert len(payload["series"]) == 10
    assert sum(row["kg"] for row in payload["series"]) == 1000.0

    other = servant_305_client.get(f"/api/dashboard?start={START}&end={END}").get_json()
    assert other["stats"]["total_weight"] == 595.0
    assert other["stats"]["present_days"] == 6
    assert other["stats"]["attendance_pct"] == 60


def test_servant_gauge_shape(servant_client):
    gauge = servant_client.get(f"/api/dashboard?start={START}&end={END}").get_json()["gauge"]

    # The gauge tracks the *current cycle* window, not the requested range, so
    # assert its shape rather than its rate: with the fixture dates in the past
    # that window holds no attendance and the bracket is always < 70%.
    assert set(gauge) == GAUGE_KEYS
    assert gauge["cycle_days"] == 10
    assert gauge["rate_unit"] == "kg"

    span = date.fromisoformat(gauge["cycle_end"]) - date.fromisoformat(gauge["cycle_start"])
    assert span.days == CYCLE_DAYS - 1


def test_dashboard_requires_login_and_validates_the_range(client, owner_client):
    assert client.get("/api/dashboard").status_code == 401

    assert owner_client.get("/api/dashboard?start=bad&end=bad").status_code == 400
    assert owner_client.get(f"/api/dashboard?start={END}&end={START}").status_code == 400


# ---------------------------------------------------------------------------
# GET /api/servant/records
# ---------------------------------------------------------------------------
def test_records_are_servant_only(owner_client, supervisor_client):
    assert owner_client.get("/api/servant/records").status_code == 403
    assert supervisor_client.get("/api/servant/records").status_code == 403


def test_records_before_any_run(servant_client):
    payload = servant_client.get("/api/servant/records").get_json()

    assert payload["history"] == []
    assert len(payload["weights"]) == 10
    assert len(payload["attendance"]) == 10
    assert set(payload["gauge"]) == GAUGE_KEYS

    newest = payload["weights"][0]  # ordered newest first
    assert newest["work_date"] == END
    assert newest["adjusted_weight"] == 100.0
    assert newest["rainy_day"] == 0

    assert all(row["status"] == "Present" for row in payload["attendance"])
    assert payload["attendance"][0]["work_date"] == END
    assert payload["attendance"][0]["check_in"] == "07:30"


def test_records_include_the_rainy_day_and_salary_history(
    servant_client, servant_305_client, make_run
):
    # 305's oldest weighing is the rainy one: 100 kg raw -> 95 kg adjusted.
    weights = servant_305_client.get("/api/servant/records").get_json()["weights"]
    rainy = weights[-1]
    assert rainy["work_date"] == START
    assert rainy["rainy_day"] == 1
    assert rainy["original_weight"] == 100.0
    assert rainy["adjusted_weight"] == 95.0

    make_run()

    history = servant_client.get("/api/servant/records").get_json()["history"]
    assert len(history) == 1
    assert history[0]["period_start"] == START
    assert history[0]["period_end"] == END
    assert history[0]["attendance_pct"] == 100
    assert history[0]["total_weight"] == 1000.0
    assert history[0]["total_salary"] == 60000
    assert history[0]["status"] == "Pending"


def test_records_never_leak_another_servant(servant_305_client):
    payload = servant_305_client.get("/api/servant/records").get_json()

    assert {row["servant_id"] for row in payload["weights"]} == {305}
    assert {row["servant_id"] for row in payload["attendance"]} == {305}
