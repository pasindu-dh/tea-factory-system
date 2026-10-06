"""Tea Factory System — Flask application factory and CLI."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import click
from flask import Flask, jsonify, render_template

import db as db_module
from api import register_api
from auth import bp as auth_bp
from config import Config, load_or_create_secret_key
from helpers import register_error_handlers

BASE_CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)
# The frontend contains no inline handlers or inline <script> blocks, so the
# strict policy below can block inline script entirely.
SCRIPT_SRC = "'self'"


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.json.sort_keys = False

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = load_or_create_secret_key(Path(app.instance_path))

    db_module.init_app(app)
    app.register_blueprint(auth_bp)
    register_api(app)
    register_error_handlers(app)

    @app.errorhandler(sqlite3.IntegrityError)
    def _integrity_error(err):
        return jsonify({"error": "The change conflicts with existing data.", "code": "conflict"}), 409

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault(
            "Content-Security-Policy",
            f"script-src {app.config.get('CSP_SCRIPT_SRC', SCRIPT_SRC)}; {BASE_CSP}",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    _register_cli(app)
    return app


def _register_cli(app: Flask) -> None:
    import seed as seed_module

    @app.cli.command("init-db")
    @click.option("--force", is_flag=True, help="Delete the existing database first.")
    @click.option("--seed", "seed_data", is_flag=True, help="Load deterministic demo data.")
    @click.option("--today", default=None, help="Anchor demo data to this date (YYYY-MM-DD).")
    def init_db_command(force: bool, seed_data: bool, today: str | None):
        """Create the database and optionally seed demo data."""
        db_path = Path(app.config["DATABASE"])
        if force:
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(str(db_path) + suffix)
                if candidate.exists():
                    candidate.unlink()
            click.echo(f"Removed existing database at {db_path}")

        db_module.init_db(app)
        click.echo(f"Database ready at {db_path}")

        if seed_data:
            anchor = date.fromisoformat(today) if today else date.today()
            with app.app_context():
                counts = seed_module.seed_database(anchor)
            click.echo(
                "Seeded demo data: "
                + ", ".join(f"{name}={count}" for name, count in counts.items())
            )


app = create_app()
