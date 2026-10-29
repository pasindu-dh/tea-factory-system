# 🍃 Ceylon Tea Factory — Management System

A single-portal factory management system: attendance timecards, tea-leaf weighing with
automatic rainy-day moisture deductions, tiered 10-day payroll, payslips, and analytics.
It is a Python **Flask + SQLite** application with a server-rendered, framework-free
frontend, real login sessions, and server-enforced role permissions.

The portal is one deployable unit: Flask serves both the JSON API and the single-page
UI, so there is no separate frontend build, dev server, or CORS configuration.

## Contents

- [Features](#features)
- [Business rules](#business-rules)
- [Architecture](#architecture)
- [Local setup](#local-setup)
- [Configuration](#configuration)
- [CLI reference](#cli-reference)
- [Tests and CI](#tests-and-ci)
- [Deploying on PythonAnywhere (free)](#deploying-on-pythonanywhere-free)
- [Paid managed option: Render](#paid-managed-option-render)
- [Docker and other hosts](#docker-and-other-hosts)
- [Operations and security](#operations-and-security)
- [Project layout](#project-layout)
- [Known limits](#known-limits)
- [Troubleshooting](#troubleshooting)

## Features

### Owner (administrator)
- Add, edit, reset the password of, deactivate/reactivate, and delete Field Supervisors
  and Servants. Inactive accounts can be listed with the **Include inactive** filter.
- Assign each supervisor one or more operational sections from a checkbox group; the
  Supervisors table lists every assignment.
- Configure tiered per-kg collection rates and retail daily wages.
- Preview payroll for any completed date range.
- Compile exactly 10-day salary runs, finalize them, and pay a single line or every
  pending line.
- Record **how** each line was settled — Cash, Bank Transfer, or Cheque — with an optional
  reference such as a cheque number. It is stored per line, shown on the payslip, and
  included in both CSV exports.
- Open a payroll run to see every servant's bracket, rate, output, status, and payment
  details in one view.
- Export the run or an individual payslip as CSV; payslips also print from the browser.
- Analytics: harvest versus real payroll cost, rainy-day deduction breakdown, work-area
  distribution, and a collector productivity leaderboard.

### Field Supervisor
- Register and edit servant profiles.
- Mark daily attendance — status becomes *Present* automatically when a check-in time is
  entered.
- Review attendance history for any range, for one servant or the whole crew; the
  attendance percentage is calculated by the server.
- Record tea-bag weights with a live rainy-day deduction preview. Both Tea Collectors and
  Retail Workers can be selected; a retail worker keeps their registered work type.
- Assign each servant a daily work area.
- See operational dashboard figures (staffing, harvest, rainy deduction, area split) but
  **not** payroll costs or rates beyond the read-only rate endpoint.

### Servant (worker view)
- Live attendance ring and estimated-salary gauge for the current payroll cycle, with the
  active bracket highlighted.
- Personal ledger of weighings, check-in/out timestamps, and salary history with printable
  payslips.
- The ledger shows the **latest** 100 weighings, 60 attendance rows, and 12 payroll lines,
  labelled with the total record count rather than claiming complete history.

## Business rules

`payroll.py` is the single source of truth for all salary maths; the API, dashboard, and
reports all call it.

| Rule | Formula / behaviour |
|---|---|
| Rainy-day moisture deduction | `adjusted = original − original / 20` (1 kg per 20 kg) |
| Tea Collector pay | `adjusted kg × bracket rate` |
| — bracket > 80 % | Rs. 60 / kg (configurable) |
| — bracket 70–80 % | Rs. 50 / kg (configurable) |
| — bracket < 70 % | Rs. 40 / kg (configurable) |
| Retail Worker pay | `present days × gender daily wage` (Male Rs. 2,000 / Female Rs. 1,500 defaults) |
| Weighing eligibility | any active Tea Collector **or** Retail Worker; retail weighings count toward harvest, area, rainy-day, and leaderboard reports but never change retail pay |
| Payroll cycle | exactly 10 days; each run snapshots the rates in force at compile time |
| Compile eligibility | the cycle's final day must be **strictly before today**; an in-progress cycle is rejected with `422 cycle_incomplete` |
| Overlap protection | two runs may not share a day; an overlapping range is rejected with `409 overlapping_run` |
| Future dates | attendance summaries, reports, dashboards, and payroll previews reject `end > today`; UI date defaults are clipped to the server's today |
| Attendance percentage | computed once in `payroll.attendance_pct` (half-up rounding); no screen re-derives it |

A cycle ending today can be compiled tomorrow, once the final day's attendance and weights
are recorded.

## Architecture

| Layer | Choice |
|---|---|
| Backend | Python 3.12+ / Flask 3; Waitress in Docker, or the host's WSGI server |
| Database | SQLite with WAL, foreign keys on, one request-scoped connection, 5 s busy timeout |
| Schema changes | frozen `schema.sql` baseline + numbered migrations tracked by `PRAGMA user_version` |
| Frontend | Jinja-rendered single page, vanilla JS modules, custom CSS, vendored Chart.js and Feather icons, self-hosted fonts |
| Auth | signed HttpOnly session cookies, Werkzeug password hashes, server-side role decorators |
| Tests | pytest (API + payroll engine), pyflakes, optional Playwright browser smoke test |
| Containers | `Dockerfile` + `docker-entrypoint.sh`, Render Blueprint in `render.yaml` |

**Request flow:** the browser calls same-origin `/api/...` endpoints with
`credentials: 'same-origin'`. The Content-Security-Policy allows no external origins, and
all assets are local, so the portal works on an offline factory LAN.

Writes that span multiple rows — payroll run creation, paying a run, bulk attendance,
bulk assignments, seeding — run inside a `db.transaction()` (`BEGIN IMMEDIATE`) and roll
back completely on failure. The migration runner executes each file statement-by-statement
inside one transaction, so a failed migration leaves both the schema and the version
untouched.

## Local setup

### Windows

Python 3.12 or newer is required. If it is not installed:

```powershell
winget install -e --id Python.Python.3.12
```

From the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt -r requirements-dev.txt
flask --app app init-db --seed        # create instance/tea_factory.sqlite3 + demo data
flask --app app run --host=0.0.0.0 --port=5000
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
flask --app app init-db --seed
flask --app app run --host=0.0.0.0 --port=5000
```

Open <http://127.0.0.1:5000>. Other devices on the same network can use
`http://<this-machine-ip>:5000`.

For a longer-running LAN deployment, use Waitress instead of the Flask dev server:

```powershell
waitress-serve --host=0.0.0.0 --port=5000 --threads=8 app:app
```

### Demo accounts

Demo data is deterministic and anchored to the current date: the previous 10-day cycle is
seeded with a finalized, paid payroll run, and the current cycle is seeded up to today.

| Role | Phone | Password |
|---|---|---|
| Owner | 0771112222 | owner123 |
| Supervisor | 0773334444 | super123 |
| Supervisor | 0775556666 | super123 |
| Tea Collector | 0777778888 | servant123 |
| Tea Collector | 0779990000 | servant123 |
| Retail Worker | 0772223333 | servant123 |
| Retail Worker | 0774445555 | servant123 |

The passwords are hidden from the sign-in screen by default. To show them on a demo
install, set `TEA_FACTORY_SHOW_DEMO_CREDENTIALS=1`. Never enable that in production, and
never run `init-db --seed` against a real database. Reset demo data with
`flask --app app init-db --force --seed`.

## Configuration

Variables are read from the process environment. **Nothing auto-loads `.env`**
(`python-dotenv` is deliberately not a dependency); use your shell, a service manager, or
`flask --env-file` if you install it yourself.

| Variable | Default | Purpose |
|---|---|---|
| `TEA_FACTORY_DB` | `instance/tea_factory.sqlite3` | SQLite file path. Use a persistent volume in production. |
| `TEA_FACTORY_SECRET_KEY` | generated into `instance/secret_key` | Session signing key. Production requires 32+ random characters from the environment. |
| `TEA_FACTORY_SECURE_COOKIES` | `0` | Set `1` only when served over HTTPS. |
| `TEA_FACTORY_SHOW_DEMO_CREDENTIALS` | `0` | Show demo passwords on the sign-in screen. |
| `TEA_FACTORY_PRODUCTION` | `0` | Enables fail-fast production checks and refuses `init-db --seed`. |
| `TEA_FACTORY_TRUST_PROXY` | `0` | Trust one `X-Forwarded-*` hop (Render/PaaS). Required so the login throttle sees real client IPs. |
| `PORT` | `8000` | Port used by the container entrypoint. |
| `TZ` | system | Set `Asia/Colombo` in containers so "today" matches the factory's day. |

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Production mode refuses to start if the secret is absent or too short, secure cookies are
off, or demo credentials are enabled.

## CLI reference

Run all commands as the account that owns the database (in the container, the `app` user).

| Command | Purpose |
|---|---|
| `flask --app app init-db [--force] [--seed] [--today YYYY-MM-DD]` | Create/upgrade the schema and insert default rates; optionally load demo data. |
| `flask --app app create-owner` | Interactive first-owner bootstrap for a real install. Prompts for name, phone, gender, and password; refuses duplicate phones. |
| `flask --app app migrate [--status]` | Apply pending numbered migrations, or show the current and pending versions. |
| `flask --app app backup-db [--output PATH] [--force]` | Consistent online backup using SQLite's backup API; verifies `integrity_check` and row counts. |

`init-db` is idempotent and is also what the container entrypoint runs on every boot: it
applies pending migrations and inserts the default `rate_config` row if it is missing. The
web process itself never runs DDL.

## Tests and CI

```bash
python -m pytest -q
```

Use `python -m pytest`, not bare `pytest`: there is no root `conftest.py` or `pytest.ini`,
so only the module form puts the project root on `sys.path`.

The suite currently collects **188 tests** covering the payroll engine (rainy maths,
bracket boundaries at exactly 70 %/80 %, half-up rounding, cycle helpers), authentication
and session revocation, role enforcement, every API endpoint, transactional rollback,
CSV-injection escaping, migration atomicity, validation, health checks, production config,
the CLI, payslip/CSV export, and the reports aggregates.

```bash
python -m pyflakes app.py config.py db.py auth.py helpers.py payroll.py seed.py migrate.py api tests
```

GitHub Actions runs pytest on Python 3.12 and 3.13, runs pyflakes, and builds the Docker
image and polls `/healthz` inside a running container.

### Browser smoke test

The pytest suite is API-level. `tests/browser_smoke.py` drives a real Chromium through the
running portal and checks the payroll run modal, paying a line, the payslip stacking above
the run modal, attendance history, and console/CSP hygiene. It starts its own server on a
free port with a throwaway database.

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium       # one-off browser download
python -m tests.browser_smoke               # headless
python -m tests.browser_smoke --headed --artifacts .\shots
```

It is not collected by pytest and not run in CI because the browser download is large.

## Deploying on PythonAnywhere (free)

SQLite needs a persistent filesystem, and **PythonAnywhere's free tier provides one**: a
home directory that survives restarts, one web app on
`https://<username>.pythonanywhere.com`, 512 MB of storage, and a daily CPU allowance. It
does not offer a custom domain on free accounts. This is the recommended zero-cost host.

1. Create a free account at <https://www.pythonanywhere.com> and open a **Bash console**.
2. Clone the repository and install the runtime dependencies (if the repository is
   private, use a GitHub token or upload a ZIP instead):
   ```bash
   cd ~
   git clone https://github.com/pasindu-dh/tea-factory-system.git
   cd tea-factory-system
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Generate a session secret once. Keep the output — the console and the WSGI file must use
   the same value:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
4. Create the database and first owner. Production mode needs the same environment the WSGI
   file will set, so export these first (replace `USERNAME` and `SECRET`):
   ```bash
   export TEA_FACTORY_DB=/home/USERNAME/tea-factory-data/tea_factory.sqlite3
   export TEA_FACTORY_SECRET_KEY=SECRET
   export TEA_FACTORY_PRODUCTION=1
   export TEA_FACTORY_SECURE_COOKIES=1
   mkdir -p /home/USERNAME/tea-factory-data
   flask --app app init-db
   flask --app app create-owner
   ```
   `create-owner` prompts for the owner's name, phone, gender, and password. Do not load
   demo data on a real installation.

   For a throwaway public demo instead, skip production mode and seed the documented demo
   accounts with `TEA_FACTORY_PRODUCTION=0 flask --app app init-db --seed`. Anyone can sign
   in as the owner of a demo, so never put real data in it.
5. On the **Web** tab: **Add a new web app → Manual configuration**, choose Python 3.12
   (or the newest available), then set:
   - **Source code**: `/home/USERNAME/tea-factory-system`
   - **Working directory**: `/home/USERNAME/tea-factory-system`
   - **Virtualenv**: `/home/USERNAME/tea-factory-system/.venv`
   - Open the **WSGI configuration file** link and replace its contents with
     [`deploy/pythonanywhere_wsgi.py`](deploy/pythonanywhere_wsgi.py), substituting
     `YOUR_USERNAME` and `PASTE_A_64_CHAR_SECRET`.
6. Click **Reload**, then open `https://USERNAME.pythonanywhere.com`. If it errors, check
   the Web tab's error log; the usual causes are a placeholder secret or a database that
   was never initialized.
7. Sign in with the owner account and create staff. Static files are served by Flask, so no
   separate static mapping is required.

Free-tier CPU is limited. The app is small, but very large CSV exports or repeated report
loads can exhaust the daily allowance.

### Updating a PythonAnywhere deployment

In a Bash console, with the same environment variables as step 4:

```bash
cd ~/tea-factory-system
source .venv/bin/activate
export TEA_FACTORY_DB=/home/USERNAME/tea-factory-data/tea_factory.sqlite3
export TEA_FACTORY_SECRET_KEY=SECRET
export TEA_FACTORY_PRODUCTION=1
export TEA_FACTORY_SECURE_COOKIES=1
flask --app app backup-db        # SQLite online backup, before any upgrade
git pull
pip install -r requirements.txt  # no-op when requirements.txt is unchanged
flask --app app migrate --status # show current and pending schema versions
flask --app app migrate          # apply pending migrations (never resets data)
```

Run the migration **before** clicking Reload: new application code expects the schema it
ships with. Then click **Reload** on the Web tab. Free accounts have no automatic database
backups, so download or copy `instance/backups/` (or the output path you chose) from time to
time.
PythonAnywhere runs the app under uWSGI, not Waitress; the in-process login throttle still
works because the free tier runs one worker.

## Paid managed option: Render

If you later want a custom domain, managed TLS, and disk snapshots, `render.yaml` deploys the
Docker image to a Render **Starter** instance with a **1 GB persistent disk** (roughly
$7/month plus a small per-GB charge). Render's free web services have an ephemeral
filesystem, so SQLite writes would disappear on restart — do not use the free plan for this
app.

1. Push the repository to GitHub.
2. Render: **New → Blueprint**, connect the repository, and apply the Blueprint. Review:
   Docker runtime, Starter plan, Singapore, 1 GB disk at `/data`, health check `/healthz`,
   generated secret, secure cookies, production mode, proxy trust, demo credentials off,
   `TZ=Asia/Colombo`.
3. After a green health check, open the Render Shell and run as the `app` user:
   ```bash
   setpriv --reuid=app --regid=app --init-groups flask --app app create-owner
   ```
   Never run CLI commands as root against the app-owned database; root-owned `-wal`/`-shm`
   files cause "attempt to write a readonly database".
4. Before each migration, back up as `app`:
   `setpriv --reuid=app --regid=app --init-groups flask --app app backup-db`.
   Then push; the entrypoint migrates before serving.
5. Keep exactly one instance. SQLite has a single writer, and one disk can only be mounted
   by one instance.

## Docker and other hosts

Build and run locally:

```bash
docker build -t tea-factory .
docker run --rm -d --name tea-factory -p 8000:8000 \
  -v tea-factory-data:/data \
  -e TEA_FACTORY_PRODUCTION=0 \
  -e TEA_FACTORY_SECURE_COOKIES=0 \
  -e TEA_FACTORY_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  tea-factory
```

Then open <http://127.0.0.1:8000>, check `curl http://127.0.0.1:8000/healthz`, and create
an owner with:

```bash
docker exec -it -u app tea-factory flask --app app create-owner
```

The image works on any container host that provides a persistent volume and a `PORT`
variable. It expects to be mounted at the site root (`/api/...` URLs are absolute).

## Operations and security

- **Roles** are enforced server-side on every route; the UI only mirrors them.
- **Passwords** are hashed with Werkzeug. A password change or owner reset invalidates the
  user's other browser sessions immediately (a keyed fingerprint of the stored hash lives in
  the signed session).
- **Forced password change:** after an owner reset, only `/api/auth/me`, the password-change
  endpoint, and logout are allowed until the temporary password is replaced. The modal is
  not dismissible.
- **Secret rotation** logs every session out. Keep the key in the host's secret manager.
- **CSV exports** escape cells that begin with `= + - @`, tab, or carriage return, so a
  malicious payment reference cannot execute as a spreadsheet formula.
- **Request bodies** are capped at 1 MB; `NaN`/`Infinity` and absurdly large numbers are
  rejected.
- **Login throttle** is in-process: ten failures per client IP in five minutes. It depends
  on a single worker process (Waitress, or uWSGI on PythonAnywhere); with
  `TEA_FACTORY_TRUST_PROXY=1` behind a proxy it keys on the real client address rather than
  the proxy's.
- **Health** is `GET /healthz` (no auth): it runs a database query and returns 503 if the
  database is unusable.
- **Sessions** last 12 hours and run over HTTPS in production. `TEA_FACTORY_SECURE_COOKIES`
  must stay off for plain-HTTP LAN use.
- **Timezone:** payroll and attendance rules use "today". In containers set
  `TZ=Asia/Colombo`; a UTC host would roll over at 05:30 local time.
- **Backups:** schedule `flask --app app backup-db` (SQLite's online backup API, not a file
  copy; WAL commits may live in the `-wal` sidecar). Verify the printed `integrity ok` line.

## Project layout

```
app.py                  Flask factory, security headers, /healthz, CLI commands
config.py               Domain constants, environment config, production checks
schema.sql              SQLite schema — FROZEN version 0 baseline
migrate.py              Ordered migrations driven by PRAGMA user_version
migrations/             Numbered .sql files; every schema change goes here
db.py                   Request-scoped SQLite connection, transactions
auth.py                 Sessions, password fingerprints, roles, login throttle
payroll.py              Pure payroll engine — no Flask/DB imports
seed.py                 Deterministic demo data
api/                    Blueprints: users, attendance, weights, assignments, rates,
                        payroll (payroll_api), dashboard, reports
templates/index.html    Single-page UI
static/                 css/, js/ (api.js, ui.js, app.js), vendored Chart.js & Feather,
                        self-hosted fonts/, img/
tests/                  pytest suite + browser_smoke.py (Playwright)
.github/                CI workflow (tests, lint, container health check)
Dockerfile              Production image
docker-entrypoint.sh    Volume ownership, init/migrate, Waitress on $PORT
render.yaml             Render Blueprint: Starter + 1 GB persistent disk
deploy/                 PythonAnywhere WSGI configuration template
.env.example            Documented environment variables
instance/               SQLite database + generated secret key (gitignored)
```

## Known limits

- The app must be mounted at the site root; there is no path-prefix support.
- One instance only. SQLite and the in-process login throttle both assume a single process.
- No pagination: payroll run history shows the latest 25 runs; the servant ledger shows the
  latest 100 weighings / 60 attendance rows / 12 salary lines (the UI labels the totals).
- No self-service registration, forgot-password email, SMS, or PDF export (browser print
  and CSV only).
- No multi-factory tenancy, audit-log screen, or i18n.

## Troubleshooting

**`ModuleNotFoundError: No module named 'flask'`**
The virtualenv is not active, or you are using another Python. Activate it, or invoke the
venv interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m flask --app app init-db --seed
```

**`Error: [Errno 10048] ... only one usage of each socket address`**
Port 5000 is taken. Find and stop the process, or serve elsewhere:

```powershell
netstat -ano | findstr :5000
taskkill /PID <pid> /F
waitress-serve --host=0.0.0.0 --port=5001 app:app
```

**Other devices cannot reach the app**
Allow the port through Windows Firewall (Administrator shell) and confirm the devices are
on the same subnet:

```powershell
netsh advfirewall firewall add rule name="Tea Factory" dir=in action=allow protocol=TCP localport=5000
```

**Render: `unable to open database file`**
The persistent disk is not writable by the app user. Confirm the disk is mounted at
`/data`, `TEA_FACTORY_DB=/data/tea_factory.sqlite3`, and the entrypoint is running (it
starts as root, chowns `/data`, then drops to `app`). Do not run CLI commands as root.

**PythonAnywhere: the web app returns 500 / `RuntimeError: TEA_FACTORY_PRODUCTION=1 requires ...`**
The placeholder secret in `deploy/pythonanywhere_wsgi.py` was not replaced, or the Web
app's virtualenv/source path is wrong. Production mode requires
`TEA_FACTORY_SECRET_KEY` (32+ random characters, set in the WSGI file),
`TEA_FACTORY_SECURE_COOKIES=1`, and `TEA_FACTORY_SHOW_DEMO_CREDENTIALS=0`.

**PythonAnywhere: `no such table: users` or login fails with 500**
The database was not initialized, or the console and WSGI file point at different paths.
Run `flask --app app init-db` (and `create-owner`) in a console with the same
`TEA_FACTORY_DB` the WSGI file uses.

**PythonAnywhere: changes do not appear after `git pull`**
Click **Reload** on the Web tab. A running uWSGI worker keeps the old code loaded until the
web app is reloaded.

**Render: the service starts with a configuration error**
Production mode requires `TEA_FACTORY_SECRET_KEY` (32+ random characters, from the
environment), `TEA_FACTORY_SECURE_COOKIES=1`, and `TEA_FACTORY_SHOW_DEMO_CREDENTIALS=0`.

**Render free tier has no persistent disk**
That is expected. Free services have ephemeral filesystems; SQLite writes disappear on
restart. Use a Starter instance with a disk.

**Cannot stay signed in over plain HTTP**
`TEA_FACTORY_SECURE_COOKIES=1` tells the browser to send the cookie only over HTTPS. Turn
it off for LAN HTTP, or put the app behind TLS.

**Dates are off by one on a server**
Set `TZ=Asia/Colombo` (or the factory's timezone). The payroll and attendance rules use the
server's local date.

**Everyone gets locked out after a few failed logins**
Behind a proxy without `TEA_FACTORY_TRUST_PROXY=1`, every request appears to come from the
proxy IP, so the login throttle is global. Enable proxy trust on Render.

**`Database is at schema version N, but this code only knows up to version M`**
The database was migrated by newer code than you are running. Refusing is deliberate;
update the application or restore an older backup.

**A schema change had no effect on an existing database**
It was added to `schema.sql`, which only creates brand-new databases. Add a numbered file
in `migrations/` instead.

**The UI looks unstyled after an upgrade**
Hard-reload (Ctrl+F5). Assets are self-hosted; no external requests are made.

**`waitress-serve` cannot find the module**
Run it from the project root (or invoke `.venv\Scripts\waitress-serve.exe` directly).
