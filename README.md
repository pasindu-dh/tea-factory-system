# 🍃 Ceylon Tea Factory — Management System

A complete tea factory management portal: attendance timecards, tea-leaf weighing with
automatic rainy-day moisture deductions, tiered 10-day payroll, payslips, and analytics —
served by a Python **Flask + SQLite** backend with real login sessions and role-based access.

## Features

### Owner (main administrator)
- Add / edit / deactivate / delete Field Supervisors and Servants (CRUD), with password resets.
- Configure payment rates: per-kg tiers by attendance bracket and retail daily wages.
- Compile, finalize, and pay **10-day salary runs**; payslips with print and CSV export.
- Deep analytics: harvest vs **real payroll cost** charts, rainy-day deduction breakdown,
  work-area distribution, and a productivity leaderboard.

### Field Supervisor
- Register new servant profiles.
- Mark daily attendance timecards — status becomes *Present* automatically on check-in.
- Record tea bag weights with a live **rainy-day deduction** preview.
- Assign every servant a **daily work area** (Tea Field A/B, Factory Processing, Packaging).

### Servant (worker view)
- Live **attendance ring** and **estimated-salary gauge** for the current payroll cycle,
  with the active rate bracket highlighted.
- Personal ledger: every weighing, every check-in/out timestamp, and salary history
  with printable payslips.

## Business rules (single source of truth: `payroll.py`)

| Rule | Formula |
|---|---|
| Rainy-day moisture deduction | `adjusted = original − original / 20` (1 kg per 20 kg) |
| Tea Collector pay | `adjusted kg × rate`, rate by attendance bracket |
| — bracket > 80 % | Rs. 60 / kg (configurable) |
| — bracket 70 – 80 % | Rs. 50 / kg (configurable) |
| — bracket < 70 % | Rs. 40 / kg (configurable) |
| Retail Worker pay | `days present × daily wage` (Male Rs. 2000 / Female Rs. 1500) |
| Payroll cycle | exactly 10 days; runs snapshot the rates in force at compile time |

Attendance percentage is computed in exactly one place (`payroll.attendance_pct`, half-up
rounding) and every screen reads it from `/api/attendance/summary` or `/api/dashboard`.

## Setup (Windows)

Python 3.12 is required. If it is not installed:

```powershell
winget install -e --id Python.Python.3.12
```

Then, from the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt -r requirements-dev.txt
flask --app app init-db --seed        # create instance/tea_factory.sqlite3 + demo data
flask --app app run --host=0.0.0.0 --port=5000
```

Open <http://127.0.0.1:5000>. Other devices on the same network can use
`http://<this-pc-ip>:5000`.

For a longer-running LAN deployment use waitress instead of the dev server:

```powershell
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

### Default accounts (demo data)

| Role | Phone | Password |
|---|---|---|
| Owner | 0771112222 | owner123 |
| Supervisor | 0773334444 | super123 |
| Supervisor | 0775556666 | super123 |
| Tea Collector | 0777778888 | servant123 |
| Tea Collector | 0779990000 | servant123 |
| Retail Worker | 0772223333 | servant123 |
| Retail Worker | 0774445555 | servant123 |

Demo data is deterministic and anchored to the real current date: the previous 10-day
cycle is seeded fully with a finalized, paid payroll run, and the current cycle is seeded
up to today. Re-run `flask --app app init-db --force --seed` to reset.

## Tests

```powershell
py -m pytest -q
```

116 tests cover the payroll engine (rainy maths, bracket boundaries at exactly 70 %/80 %,
half-up rounding, cycle helpers), authentication, role enforcement, every API endpoint,
payslip/CSV export, and the reports aggregates.

## Project layout

```
app.py            Flask factory, security headers (CSP), CLI (init-db)
config.py         Domain constants and configuration
schema.sql        SQLite schema
db.py             Request-scoped SQLite connection (WAL, foreign keys)
auth.py           Sessions, password hashing, role decorators, login throttle
payroll.py        Pure payroll engine — no Flask/DB imports
seed.py           Deterministic demo data
api/              Blueprints: users, attendance, weights, assignments, rates,
                  payroll, dashboard, reports
templates/        index.html (single-page UI)
static/           css/, js/ (api.js, ui.js, app.js), vendored Chart.js & Feather, img/
tests/            pytest suite
instance/         SQLite database + generated secret key (gitignored)
```

## Operational notes

- **Security**: passwords are hashed (Werkzeug), sessions are signed HttpOnly cookies,
  roles are enforced server-side, all rendered user input is escaped, and a strict
  Content-Security-Policy blocks inline script.
- **OneDrive**: the default database lives in `instance/`. If you sync this folder with
  OneDrive, point the database elsewhere for reliability, e.g.
  `$env:TEA_FACTORY_DB = "$env:LOCALAPPDATA\TeaFactory\tea_factory.sqlite3"`.
- **Secret key**: generated once into `instance/secret_key`; set `TEA_FACTORY_SECRET_KEY`
  to override.
- Sessions run over plain HTTP on the LAN. Put the app behind HTTPS if it is ever exposed
  beyond the local network (then set `SESSION_COOKIE_SECURE`).
