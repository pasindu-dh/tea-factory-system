"""Payment-rate configuration (tiered per-kg rates and retail daily wages)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from auth import login_required, require_role
from db import execute, query_one
from helpers import ApiError, parse_positive_number

bp = Blueprint("rates", __name__, url_prefix="/api/rates")

RATE_FIELDS = ("above_80", "between_70_80", "below_70", "male_daily", "female_daily")


def get_rates() -> dict:
    row = query_one("SELECT * FROM rate_config WHERE id = 1")
    if row is None:
        raise ApiError("Rate configuration is missing.", 500, "rates_missing")
    return {field: float(row[field]) for field in RATE_FIELDS}


@bp.get("")
@login_required
def read_rates():
    row = query_one("SELECT updated_at FROM rate_config WHERE id = 1")
    return jsonify(
        {
            "rates": get_rates(),
            "updated_at": row["updated_at"] if row else None,
        }
    )


@bp.put("")
@require_role("owner")
def update_rates():
    data = request.get_json(silent=True) or {}
    values = {
        field: parse_positive_number(data.get(field), field) for field in RATE_FIELDS
    }
    execute(
        """UPDATE rate_config
              SET above_80 = ?, between_70_80 = ?, below_70 = ?,
                  male_daily = ?, female_daily = ?,
                  updated_at = datetime('now'), updated_by = ?
            WHERE id = 1""",
        (*values.values(), g.current_user["user_id"]),
    )
    return jsonify({"rates": values})
