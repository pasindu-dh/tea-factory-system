"""Rate configuration reads: who may read, what comes back, and snapshot isolation."""
from __future__ import annotations

EXPECTED_RATES = {
    "above_80": 60.0,
    "between_70_80": 50.0,
    "below_70": 40.0,
    "male_daily": 2000.0,
    "female_daily": 1500.0,
}


def test_read_rates_matches_fixture(owner_client):
    response = owner_client.get("/api/rates")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["rates"] == EXPECTED_RATES
    # The fixture inserts rate_config without updated_at, so the column default
    # must have supplied a real timestamp.
    assert isinstance(payload["updated_at"], str)
    assert payload["updated_at"]


def test_rates_are_readable_by_every_role_but_401_when_anonymous(
    client, supervisor_client, servant_client
):
    # Servants need the bracket rates for their own dashboard gauge.
    for logged_in in (supervisor_client, servant_client):
        assert logged_in.get("/api/rates").status_code == 200
    assert client.get("/api/rates").status_code == 401


def test_put_then_get_round_trips(owner_client):
    updated = dict(EXPECTED_RATES, above_80=61.0)
    response = owner_client.put("/api/rates", json=updated)
    assert response.status_code == 200
    assert response.get_json()["rates"] == updated

    assert owner_client.get("/api/rates").get_json()["rates"] == updated


def test_run_snapshot_is_isolated_from_later_rate_changes(owner_client, make_run):
    run = make_run()
    run_id = run["run"]["run_id"]
    assert run["run"]["rates"]["above_80"] == 60.0

    owner_client.put("/api/rates", json=dict(EXPECTED_RATES, above_80=99.0))

    # The compiled run keeps the rates in force when it was compiled...
    detail = owner_client.get(f"/api/payroll/runs/{run_id}").get_json()
    assert detail["run"]["rates"]["above_80"] == 60.0
    # ...even though paying a line is still allowed afterwards.
    assert owner_client.post(f"/api/payroll/runs/{run_id}/pay").status_code == 200

    # ...while the live configuration moves on.
    assert owner_client.get("/api/rates").get_json()["rates"]["above_80"] == 99.0


def test_rates_are_owner_writable_only(supervisor_client, servant_client):
    for logged_in in (supervisor_client, servant_client):
        response = logged_in.put("/api/rates", json=EXPECTED_RATES)
        assert response.status_code == 403


def test_rates_reject_non_positive_and_non_numeric_values(owner_client):
    for bad_value in (0, -5, "abc", None):
        response = owner_client.put("/api/rates", json=dict(EXPECTED_RATES, above_80=bad_value))
        assert response.status_code == 400, bad_value
        assert response.get_json()["code"] == "invalid_number"
