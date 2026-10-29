"""Payroll preview, 10-day enforcement, runs, payment, payslips, and exports."""
from __future__ import annotations

from datetime import date, timedelta

import db as db_module
from conftest import EXPECTED_SALARIES, PERIOD_END, PERIOD_START

START = PERIOD_START.isoformat()
END = PERIOD_END.isoformat()


def test_preview_is_non_mutating_and_allows_any_range(owner_client, row_count):
    before = (row_count("payroll_runs"), row_count("salaries"))
    response = owner_client.get("/api/payroll/preview?start=2026-09-24&end=2026-10-02")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["period_days"] == 9
    assert payload["is_cycle"] is False
    assert payload["existing_run"] is None
    assert (row_count("payroll_runs"), row_count("salaries")) == before


def test_preview_matches_expected_salaries(owner_client):
    payload = owner_client.get(f"/api/payroll/preview?start={START}&end={END}").get_json()
    assert payload["is_cycle"] is True

    by_id = {line["servant_id"]: line for line in payload["lines"]}
    for servant_id, expected in EXPECTED_SALARIES.items():
        line = by_id[servant_id]
        assert line["attendance_pct"] == expected["attendance_pct"]
        assert line["total_weight"] == expected["total_weight"]
        assert line["applied_rate"] == expected["applied_rate"]
        assert line["total_salary"] == expected["total_salary"]

    assert payload["totals"]["total_salary"] == sum(
        item["total_salary"] for item in EXPECTED_SALARIES.values()
    )


def test_run_requires_exactly_ten_days(owner_client):
    response = owner_client.post(
        "/api/payroll/runs", json={"start": "2026-09-24", "end": "2026-10-02"}
    )
    assert response.status_code == 409
    assert response.get_json()["code"] == "not_a_cycle"


def test_compile_run_creates_lines(owner_client, make_run, row_count):
    payload = make_run()
    assert payload["run"]["status"] == "draft"
    assert payload["run"]["period_days"] == 10
    assert len(payload["lines"]) == 5
    assert row_count("payroll_runs") == 1
    assert row_count("salaries") == 5

    line = next(item for item in payload["lines"] if item["servant_id"] == 301)
    assert line["total_salary"] == 60000
    assert line["status"] == "Pending"


def test_duplicate_run_rejected(owner_client, make_run):
    make_run()
    response = owner_client.post("/api/payroll/runs", json={"start": START, "end": END})
    assert response.status_code == 409
    assert response.get_json()["code"] == "duplicate_run"


def test_preview_reports_existing_run(owner_client, make_run):
    run = make_run()
    payload = owner_client.get(f"/api/payroll/preview?start={START}&end={END}").get_json()
    assert payload["existing_run"]["run_id"] == run["run"]["run_id"]
    assert len(payload["existing_run"]["lines"]) == 5


def test_rate_change_does_not_alter_existing_payslip(owner_client, make_run):
    run = make_run()
    salary_id = next(
        line["salary_id"] for line in run["lines"] if line["servant_id"] == 301
    )

    assert owner_client.put(
        "/api/rates",
        json={
            "above_80": 99,
            "between_70_80": 88,
            "below_70": 77,
            "male_daily": 3000,
            "female_daily": 2500,
        },
    ).status_code == 200

    payslip = owner_client.get(f"/api/payroll/payslips/{salary_id}").get_json()["payslip"]
    assert payslip["total_salary"] == 60000
    assert payslip["applied_rate"] == 60.0


def test_finalize_then_delete_is_blocked(owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]

    finalized = owner_client.post(f"/api/payroll/runs/{run_id}/finalize")
    assert finalized.status_code == 200
    assert finalized.get_json()["run"]["status"] == "finalized"

    response = owner_client.delete(f"/api/payroll/runs/{run_id}")
    assert response.status_code == 409
    assert response.get_json()["code"] == "run_finalized"


def test_draft_run_can_be_deleted(owner_client, make_run, row_count):
    run = make_run()
    assert owner_client.delete(f"/api/payroll/runs/{run['run']['run_id']}").status_code == 204
    assert row_count("payroll_runs") == 0


def test_pay_single_line_then_all(owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]
    first = next(line for line in run["lines"] if line["servant_id"] == 301)

    paid = owner_client.post(
        f"/api/payroll/runs/{run_id}/pay", json={"salary_ids": [first["salary_id"]]}
    )
    assert paid.status_code == 200
    lines = {line["servant_id"]: line for line in paid.get_json()["lines"]}
    assert lines[301]["status"] == "Paid"
    assert lines[301]["paid_at"] is not None
    assert lines[302]["status"] == "Pending"

    rest = owner_client.post(f"/api/payroll/runs/{run_id}/pay", json={})
    assert rest.status_code == 200
    assert all(line["status"] == "Paid" for line in rest.get_json()["lines"])

    again = owner_client.post(f"/api/payroll/runs/{run_id}/pay", json={})
    assert again.status_code == 409
    assert again.get_json()["code"] == "nothing_to_pay"


def test_pay_rejects_unknown_salary_ids(owner_client, make_run):
    run = make_run()
    response = owner_client.post(
        f"/api/payroll/runs/{run['run']['run_id']}/pay", json={"salary_ids": [99999]}
    )
    assert response.status_code == 400


def test_payslip_access_rules(owner_client, servant_client, servant_305_client, make_run):
    run = make_run()
    salary_301 = next(line for line in run["lines"] if line["servant_id"] == 301)["salary_id"]

    assert owner_client.get(f"/api/payroll/payslips/{salary_301}").status_code == 200
    assert servant_client.get(f"/api/payroll/payslips/{salary_301}").status_code == 200
    assert servant_305_client.get(f"/api/payroll/payslips/{salary_301}").status_code == 403


def test_payslip_csv_export(owner_client, make_run):
    run = make_run()
    salary_301 = next(line for line in run["lines"] if line["servant_id"] == 301)["salary_id"]

    response = owner_client.get(f"/api/payroll/payslips/{salary_301}/export?format=csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert (
        f"payslip_SRV-301_{START}_{END}.csv" in response.headers["Content-Disposition"]
    )

    body = response.get_data(as_text=True)
    assert body.startswith("﻿")  # Excel-friendly BOM
    assert "Gross salary (Rs.)" in body
    assert "60000" in body


def test_run_csv_export(owner_client, make_run):
    run = make_run()
    response = owner_client.get(f"/api/payroll/runs/{run['run']['run_id']}/export?format=csv")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "SRV-301" in body
    assert body.count("\n") >= 6  # header + 5 servants


def test_servant_salary_history(owner_client, servant_client, make_run):
    make_run()
    response = servant_client.get("/api/payroll/my-history")
    assert response.status_code == 200
    history = response.get_json()["history"]
    assert len(history) == 1
    assert history[0]["total_salary"] == 60000
    assert history[0]["status"] == "Pending"


def test_runs_listing_and_servant_filtering(owner_client, servant_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]

    listing = owner_client.get("/api/payroll/runs").get_json()["runs"]
    assert len(listing) == 1
    assert listing[0]["servant_count"] == 5
    assert listing[0]["total_salary"] == 119800  # 60000 + 20000 + 23800 + 16000 + 0

    as_servant = servant_client.get(f"/api/payroll/runs/{run_id}").get_json()
    assert len(as_servant["lines"]) == 1
    assert as_servant["lines"][0]["servant_id"] == 301


def test_owner_only_endpoints(servant_client, supervisor_client):
    assert servant_client.get(f"/api/payroll/preview?start={START}&end={END}").status_code == 403
    assert servant_client.post("/api/payroll/runs", json={"start": START, "end": END}).status_code == 403
    assert servant_client.get("/api/payroll/runs").status_code == 403
    assert supervisor_client.get(f"/api/payroll/preview?start={START}&end={END}").status_code == 403


def test_invalid_dates_rejected(owner_client):
    assert owner_client.get("/api/payroll/preview?start=nope&end=nope").status_code == 400
    assert owner_client.get(f"/api/payroll/preview?start={END}&end={START}").status_code == 400


# ---------------------------------------------------------------------------
# Payment method / reference (migration 001)
# ---------------------------------------------------------------------------
def test_pay_records_the_payment_method_and_reference(owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]
    target = next(l for l in run["lines"] if l["servant_id"] == 301)["salary_id"]

    response = owner_client.post(
        f"/api/payroll/runs/{run_id}/pay",
        json={"salary_ids": [target], "payment_method": "Bank Transfer", "payment_ref": "REF-9"},
    )
    assert response.status_code == 200

    by_id = {line["salary_id"]: line for line in response.get_json()["lines"]}
    assert by_id[target]["status"] == "Paid"
    assert by_id[target]["payment_method"] == "Bank Transfer"
    assert by_id[target]["payment_ref"] == "REF-9"

    # Untouched lines keep no payment details rather than inheriting them.
    other = next(l for l in response.get_json()["lines"] if l["servant_id"] != 301)
    assert other["status"] == "Pending"
    assert other["payment_method"] is None
    assert other["payment_ref"] is None


def test_paying_without_a_method_leaves_the_recorded_one_alone(owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]
    target = next(l for l in run["lines"] if l["servant_id"] == 301)["salary_id"]

    owner_client.post(
        f"/api/payroll/runs/{run_id}/pay",
        json={"salary_ids": [target], "payment_method": "Cash"},
    )
    # A second call that omits the method must not wipe it (COALESCE, not =).
    response = owner_client.post(f"/api/payroll/runs/{run_id}/pay", json={"salary_ids": [target]})
    assert response.status_code == 200

    by_id = {line["salary_id"]: line for line in response.get_json()["lines"]}
    assert by_id[target]["payment_method"] == "Cash"


def test_pay_rejects_an_unknown_payment_method(owner_client, make_run):
    run = make_run()
    response = owner_client.post(
        f"/api/payroll/runs/{run['run']['run_id']}/pay", json={"payment_method": "Crypto"}
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_choice"


def test_pay_rejects_an_overlong_reference(owner_client, make_run):
    run = make_run()
    response = owner_client.post(
        f"/api/payroll/runs/{run['run']['run_id']}/pay", json={"payment_ref": "X" * 61}
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "field_too_long"


def test_payslip_and_run_csv_expose_the_payment_details(owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]
    target = next(l for l in run["lines"] if l["servant_id"] == 301)["salary_id"]

    owner_client.post(
        f"/api/payroll/runs/{run_id}/pay",
        json={"salary_ids": [target], "payment_method": "Cheque", "payment_ref": "CHQ-123"},
    )

    payslip = owner_client.get(f"/api/payroll/payslips/{target}").get_json()["payslip"]
    assert payslip["payment_method"] == "Cheque"
    assert payslip["payment_ref"] == "CHQ-123"

    slip_csv = owner_client.get(f"/api/payroll/payslips/{target}/export?format=csv").get_data(as_text=True)
    assert "Cheque" in slip_csv and "CHQ-123" in slip_csv

    run_csv = owner_client.get(f"/api/payroll/runs/{run_id}/export?format=csv").get_data(as_text=True)
    assert "Payment method" in run_csv
    assert "Cheque" in run_csv and "CHQ-123" in run_csv


def test_config_exposes_the_payment_methods(owner_client):
    from config import PAYMENT_METHODS

    payload = owner_client.get("/api/config").get_json()
    assert payload["payment_methods"] == list(PAYMENT_METHODS)


def _ten_day_window_ending(end: date):
    return (end - timedelta(days=9)).isoformat(), end.isoformat()


def test_compile_rejects_a_cycle_that_has_not_finished(owner_client):
    start, end = _ten_day_window_ending(date.today())
    response = owner_client.post(
        "/api/payroll/runs", json={"start": start, "end": end}
    )
    assert response.status_code == 422
    assert response.get_json()["code"] == "cycle_incomplete"


def test_compile_rejects_a_future_cycle(owner_client):
    start, end = _ten_day_window_ending(date.today() + timedelta(days=1))
    response = owner_client.post(
        "/api/payroll/runs", json={"start": start, "end": end}
    )
    assert response.status_code == 422
    assert response.get_json()["code"] == "cycle_incomplete"


def test_preview_rejects_a_future_end_date(owner_client):
    start, end = _ten_day_window_ending(date.today() + timedelta(days=1))
    response = owner_client.get(f"/api/payroll/preview?start={start}&end={end}")
    assert response.status_code == 422
    assert response.get_json()["code"] == "future_date"


def test_overlapping_payroll_run_is_rejected(owner_client, make_run):
    make_run()
    start = (PERIOD_END - timedelta(days=4)).isoformat()
    end = (PERIOD_END - timedelta(days=4) + timedelta(days=9)).isoformat()

    response = owner_client.post("/api/payroll/runs", json={"start": start, "end": end})
    assert response.status_code == 409
    assert response.get_json()["code"] == "overlapping_run"


def test_csv_exports_neutralise_formula_injection(owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]
    salary_id = run["lines"][0]["salary_id"]

    paid = owner_client.post(
        f"/api/payroll/runs/{run_id}/pay",
        json={
            "salary_ids": [salary_id],
            "payment_method": "Cheque",
            "payment_ref": "=2+2",
        },
    )
    assert paid.status_code == 200

    run_csv = owner_client.get(f"/api/payroll/runs/{run_id}/export?format=csv")
    assert "'=2+2" in run_csv.get_data(as_text=True)

    slip_csv = owner_client.get(f"/api/payroll/payslips/{salary_id}/export?format=csv")
    assert "'=2+2" in slip_csv.get_data(as_text=True)


def test_run_creation_rolls_back_when_a_line_fails(app, owner_client, row_count):
    with app.app_context():
        db_module.execute(
            """CREATE TRIGGER fail_salary_insert
               BEFORE INSERT ON salaries
               BEGIN SELECT RAISE(ABORT, 'forced test failure'); END"""
        )
    try:
        response = owner_client.post(
            "/api/payroll/runs", json={"start": START, "end": END}
        )
        assert response.status_code == 409
    finally:
        with app.app_context():
            db_module.execute("DROP TRIGGER fail_salary_insert")

    assert row_count("payroll_runs") == 0
    assert row_count("salaries") == 0


def test_pay_run_rolls_back_when_an_update_fails(app, owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]

    with app.app_context():
        db_module.execute(
            """CREATE TRIGGER fail_salary_update
               BEFORE UPDATE ON salaries
               BEGIN SELECT RAISE(ABORT, 'forced test failure'); END"""
        )
    try:
        response = owner_client.post(f"/api/payroll/runs/{run_id}/pay", json={})
        assert response.status_code == 409
    finally:
        with app.app_context():
            db_module.execute("DROP TRIGGER fail_salary_update")

    payload = owner_client.get(f"/api/payroll/runs/{run_id}").get_json()
    assert all(line["status"] == "Pending" for line in payload["lines"])
