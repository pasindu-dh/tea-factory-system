"""Tea Factory System — Flask application factory and CLI."""
from __future__ import annotations

import mimetypes
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import click
from flask import Flask, jsonify, render_template

import db as db_module
import migrate as migrate_mod
from api import register_api
from auth import bp as auth_bp
from config import Config, load_or_create_secret_key
from helpers import register_error_handlers

# Python's mimetypes has no entry for .woff/.woff2 on this stack, so Flask would
# serve the self-hosted fonts as application/octet-stream. Browsers tolerate that,
# but content-filtering gateways (common on factory LANs) treat octet-stream as
# executable and block it. Combined with the nosniff header below, be explicit.
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")

BASE_CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self'; "
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
        return render_template(
            "index.html",
            show_demo_credentials=app.config.get("SHOW_DEMO_CREDENTIALS", False),
        )

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
            click.echo(
                "Demo accounts are listed in README.md. The sign-in screen hides them "
                "by default; set TEA_FACTORY_SHOW_DEMO_CREDENTIALS=1 to display them."
            )

    @app.cli.command("migrate")
    @click.option("--status", is_flag=True, help="List applied and pending migrations, then exit.")
    def migrate_command(status: bool):
        """Apply pending schema migrations. Run this before starting the server."""
        db_path = Path(app.config["DATABASE"])
        if not db_path.exists():
            raise click.ClickException(
                f"No database at {db_path}. Run 'flask --app app init-db' first."
            )

        if status:
            conn = sqlite3.connect(db_path)
            try:
                applied = migrate_mod.current_version(conn)
                pending = migrate_mod.pending_from(conn)
            finally:
                conn.close()

            click.echo(f"Database: {db_path}")
            click.echo(f"Schema version: {applied} (latest available: {migrate_mod.latest_version()})")
            if pending:
                click.echo("Pending: " + ", ".join(str(v) for v in pending))
            else:
                click.echo("Pending: none")
            return

        try:
            applied = migrate_mod.apply_migrations(db_path, echo=click.echo)
        except migrate_mod.MigrationError as exc:
            raise click.ClickException(str(exc))

        if not applied:
            click.echo(f"Database already at version {migrate_mod.latest_version()}")

    @app.cli.command("backup-db")
    @click.option("--output", default=None, help="Destination file (default: <db-dir>/backups/).")
    @click.option("--force", is_flag=True, help="Overwrite an existing destination file.")
    def backup_db_command(output: str | None, force: bool):
        """Take a consistent snapshot of the database while the server is running."""
        db_path = Path(app.config["DATABASE"])
        if not db_path.exists():
            raise click.ClickException(f"No database at {db_path}.")

        if output:
            target = Path(output)
        else:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            target = db_path.parent / "backups" / f"{db_path.stem}-{stamp}.sqlite3"

        if target.exists() and not force:
            raise click.ClickException(
                f"{target} already exists. Pass --force to overwrite it."
            )
        target.parent.mkdir(parents=True, exist_ok=True)

        # sqlite3's online backup API, not a file copy. In WAL mode committed
        # transactions can still live in the -wal sidecar, so copying the
        # .sqlite3 file alone can silently lose recent writes. This reads a
        # consistent snapshot through the normal read path and is safe to run
        # against a live database -- no need to stop the server. The app's
        # 5s busy_timeout means a concurrent writer just waits its turn.
        source = sqlite3.connect(db_path)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise click.ClickException(f"Backup failed integrity_check: {integrity}")
            users = destination.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            salaries = destination.execute("SELECT COUNT(*) FROM salaries").fetchone()[0]
        finally:
            destination.close()
            source.close()

        size_kb = target.stat().st_size / 1024
        click.echo(f"Backed up to {target}")
        # Plain ASCII only: the Windows console codepage mangles anything else.
        click.echo(
            f"  {size_kb:,.0f} KB | integrity ok | users={users} | salaries={salaries}"
        )


app = create_app()
