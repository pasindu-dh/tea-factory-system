"""Numeric validation and request-size hardening."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_non_finite_weights_are_rejected(owner_client, value):
    response = owner_client.post("/api/weights/preview", json={"original_weight": value})
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_number"


def test_absurdly_large_number_is_rejected(owner_client):
    response = owner_client.post(
        "/api/weights/preview", json={"original_weight": 1_000_000_001}
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_number"


def test_non_finite_rate_is_rejected(owner_client):
    response = owner_client.put(
        "/api/rates",
        json={
            "above_80": "NaN",
            "between_70_80": 50,
            "below_70": 40,
            "male_daily": 2000,
            "female_daily": 1500,
        },
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid_number"


def test_oversized_body_returns_json_413(app):
    app.config["MAX_CONTENT_LENGTH"] = 64
    client = app.test_client()
    response = client.post(
        "/api/auth/login",
        json={"phone": "0" * 200, "password": "x" * 200},
    )
    assert response.status_code == 413
    assert response.get_json()["code"] == "payload_too_large"
