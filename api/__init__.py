"""API blueprint registration."""
from __future__ import annotations

from . import assignments, attendance, dashboard, payroll_api, rates, reports, users, weights

MODULES = (users, attendance, weights, assignments, rates, payroll_api, dashboard, reports)


def register_api(app) -> None:
    for module in MODULES:
        app.register_blueprint(module.bp)
