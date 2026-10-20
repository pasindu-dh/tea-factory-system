# 🍃 Ceylon Tea Factory — Management System

A complete tea factory management portal: attendance timecards, tea-leaf weighing with
automatic rainy-day moisture deductions, tiered 10-day payroll, payslips, and analytics —
served by a Python **Flask + SQLite** backend with real login sessions and role-based access.

## Features

### Owner (main administrator)
- Add / edit / deactivate / delete Field Supervisors and Servants (CRUD), with password resets.
- Configure payment rates: per-kg tiers by attendance bracket and retail daily wages.
- Compile, finalize, and pay **10-day salary runs**; payslips with print and CSV export.
- Open any run — current or historical — to see every servant's line in one view: bracket,
  rate, output, status. Pay a single line from there without leaving the view, or pay all
  pending lines at once.
- Record **how** each salary was settled (Cash, Bank Transfer or Cheque, with an optional
  reference such as a cheque number) so cash and bank payouts can be reconciled. It shows on
  the payslip and in both CSV exports.
- Deep analytics: harvest vs **real payroll cost** charts, rainy-day deduction breakdown,
  work-area distribution, and a productivity leaderboard.

### Field Supervisor
- Register new servant profiles.
- Mark daily attendance timecards — status becomes *Present* automatically on check-in.
- Review **attendance history** over any date range, for one servant or the whole crew. The
  attendance percentage shown there is the server's own figure, not a client-side estimate.
- Record tea bag weights with a live **rainy-day deduction** preview.
- Assign every servant a **daily work area** (Tea Field A/B, Factory Processing, Packaging Section).

### Servant (worker view)
- Live **attendance ring** and **estimated-salary gauge** for the current payroll cycle,
  with the active rate bracket highlighted.
- Personal ledger: every weighing, every check-in/out timestamp, and salary history
  with printable payslips showing when and how each payment was made.

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
rounding). It is exposed by `/api/attendance/summary`, `/api/dashboard`,
`/api/payroll/preview`, `/api/reports/leaderboard`, and `/api/servant/records` — no screen
re-derives it.

## Setup (Windows)

Python 3.12 or newer is required (CI runs 3.12; local development uses 3.13). If it is
not installed:

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

## Default accounts (demo data)

| Role | Phone | Password |
|---|---|---|
| Owner | 0771112222 | owner123 |
| Supervisor | 0773334444 | super123 |
| Supervisor | 0775556666 | super123 |
| Tea Collector | 0777778888 | servant123 |
| Tea Collector | 0779990000 | servant123 |
| Retail Worker | 0772223333 | servant123 |
| Retail Worker | 0774445555 | servant123 |

These passwords are **not** shown on the sign-in screen. To display them there (handy for
a demo), start the app with `TEA_FACTORY_SHOW_DEMO_CREDENTIALS=1`:

```powershell
$env:TEA_FACTORY_SHOW_DEMO_CREDENTIALS = "1"
flask --app app run --host=0.0.0.0 --port=5000
```

Demo data is deterministic and anchored to the real current date: the previous 10-day
cycle is seeded fully with a finalized, paid payroll run, and the current cycle is seeded
up to today. Re-run `flask --app app init-db --force --seed` to reset.

## Deploying and upgrading

Every step below is safe to run against a live database.

```powershell
# 1. Back up first — always, and before any upgrade.
flask --app app backup-db

# 2. See where the schema stands, then bring it up to date.
flask --app app migrate --status
flask --app app migrate

# 3. Start the server (never before step 2 — the app does not auto-migrate).
waitress-serve --host=0.0.0.0 --port=5000 --threads=8 app:app
```

**Schema changes.** `schema.sql` is the frozen *version 0* baseline; it only ever creates a
brand-new database. Every later change is a numbered file in `migrations/`, applied by
`flask migrate` and tracked in SQLite's `PRAGMA user_version`. Never edit `schema.sql` to add
a column — existing installations would never receive it. Migration is an explicit operator
step on purpose: it is not run at application startup, because two workers starting together
would race and the serving process should not perform DDL.

Note that `AREAS` and `CYCLE_DAYS` from `config.py` are repeated in `schema.sql` CHECK
constraints, so changing either needs a migration that rebuilds the table.

**Backups.** `flask backup-db` uses SQLite's online backup API, not a file copy. In WAL mode
committed transactions can still sit in the `-wal` sidecar, so copying the `.sqlite3` file
alone can silently lose recent writes. It verifies `integrity_check` and reports row counts
at creation time, so a bad backup is caught now rather than at restore. Schedule it nightly:

```powershell
schtasks /create /tn "Tea Factory Backup" /sc daily /st 22:00 ^
  /tr "cmd /c cd /d D:\Project\tea-factory-system && .venv\Scripts\flask --app app backup-db"
```

**HTTPS.** Sessions run over plain HTTP on the LAN, which is fine for a private network.
To put the app behind HTTPS, terminate TLS in front of it (Caddy, nginx, or an IIS reverse
proxy), then set `TEA_FACTORY_SECURE_COOKIES=1` and restart — otherwise the Secure cookie
flag will stop anyone signing in over plain HTTP. Also set `TEA_FACTORY_SECRET_KEY` so
sessions survive a rebuild, and add `werkzeug.middleware.proxy_fix.ProxyFix` if the proxy
sends `X-Forwarded-Proto`.

**Concurrency.** waitress runs a single process by default, which is why the in-process login
throttle is effective; running multiple worker processes splits that throttle across them.
SQLite allows one writer at a time — the 5 s busy timeout is ample for a factory's load.

See `.env.example` for every supported environment variable.

## Tests

```powershell
py -m pytest -q
```

153 tests cover the payroll engine (rainy maths, bracket boundaries at exactly 70 %/80 %,
half-up rounding, cycle helpers), authentication, role enforcement, every API endpoint —
including `/api/config`, `/api/dashboard`, `/api/servant/records` and `/api/rates` —
payslip/CSV export, the reports aggregates, and the schema migrations.

Use `py -m pytest`, not a bare `pytest`: there is no root `conftest.py` or `pytest.ini`,
so only the module form puts the project root on `sys.path`.

The suite runs in well under a minute — around 15 seconds on an idle machine. It used to
take nearly 7 minutes, almost entirely in setup: every test builds a throwaway database, and
the fixture seeded ~130 rows through `db.execute()` — one commit each — while hashing seven
passwords with Werkzeug's scrypt (~85 ms per hash). Seeding now runs in a single transaction,
and `tests/conftest.py` swaps scrypt for `pbkdf2:sha256:1000` for the duration of the test
session. Only the hashing *creation* side is substituted; logins still go through
`check_password_hash` against a real stored hash, so the verification path is unchanged.

## Browser smoke test

The pytest suite is API-level. `tests/browser_smoke.py` covers the interactive
flows it cannot reach — the payroll run-detail modal and the attendance history
card — by driving a real Chromium through the running portal and asserting on
rendered DOM. It also fails on any Content-Security-Policy violation or uncaught
JS error, and writes screenshots of each screen.

```powershell
pip install -r requirements-dev.txt
py -m playwright install chromium       # one-off browser download
py -m tests.browser_smoke               # or: py tests/browser_smoke.py
py -m tests.browser_smoke --headed --artifacts .\shots
```

It starts its own server on a free port with a throwaway database, so it never
touches `instance/`. It is not part of `pytest` and not run in CI — the browser
download is too large to justify on every push.

## Project layout

```
app.py            Flask factory, security headers (CSP), CLI (init-db, migrate, backup-db)
config.py         Domain constants and configuration
schema.sql        SQLite schema — FROZEN version 0 baseline, see migrations/
migrate.py        Ordered migrations driven by PRAGMA user_version
migrations/       Numbered .sql files; every schema change goes here
db.py             Request-scoped SQLite connection (WAL, foreign keys)
auth.py           Sessions, password hashing, role decorators, login throttle
payroll.py        Pure payroll engine — no Flask/DB imports
seed.py           Deterministic demo data
api/              Blueprints: users, attendance, weights, assignments, rates,
                  payroll (module payroll_api), dashboard, reports
templates/        index.html (single-page UI)
static/           css/, js/ (api.js, ui.js, app.js), vendored Chart.js & Feather,
                  self-hosted fonts/, img/
tests/            pytest suite + browser_smoke.py (Playwright, not collected by pytest)
.github/          CI workflow
.env.example      Documented environment variables
instance/         SQLite database + generated secret key (gitignored)
```

## Operational notes

- **Security**: passwords are hashed (Werkzeug), sessions are signed HttpOnly cookies,
  roles are enforced server-side, all rendered user input is escaped, and a strict
  Content-Security-Policy blocks inline script. The CSP allows no external origins at all —
  fonts and JS are self-hosted in `static/`, so the portal works with no internet access.
- **OneDrive**: the default database lives in `instance/`. If you sync this folder with
  OneDrive, point the database elsewhere for reliability, e.g.
  `$env:TEA_FACTORY_DB = "$env:LOCALAPPDATA\TeaFactory\tea_factory.sqlite3"`.
- **Secret key**: generated once into `instance/secret_key`; set `TEA_FACTORY_SECRET_KEY`
  to override. Keep it out of version control — `.env` is gitignored for exactly this reason.
- **Demo credentials** are hidden on the sign-in screen by default. Set
  `TEA_FACTORY_SHOW_DEMO_CREDENTIALS=1` to show them (demo installs only).
- **Sessions** run over plain HTTP on the LAN. Put the app behind HTTPS if it is ever
  exposed beyond the local network, then set `TEA_FACTORY_SECURE_COOKIES=1` — see
  "Deploying and upgrading" above.
- **Upgrades**: `flask --app app backup-db` then `flask --app app migrate`, before starting
  the new version. The application never migrates itself.

## Troubleshooting

**`ModuleNotFoundError: No module named 'flask'`**
The virtualenv is not active, or you are using a different Python. Activate it
(`.\.venv\Scripts\Activate.ps1`) or invoke the venv's own executable directly — note there
is no `py` inside `.venv\Scripts`, only `python.exe`:

```powershell
.\.venv\Scripts\python.exe -m flask --app app init-db --seed
```

Nothing in this project installs globally.

**`Error: [Errno 10048] ... only one usage of each socket address`**
Something already holds port 5000. Find and stop it, or serve on another port:

```powershell
netstat -ano | findstr :5000          # last column is the PID
taskkill /PID <pid> /F
waitress-serve --host=0.0.0.0 --port=5001 app:app
```

**Other devices cannot reach the app**
Windows Firewall is blocking inbound connections. Allow the port (needs an Administrator
shell), and check that the devices are on the same subnet:

```powershell
netsh advfirewall firewall add rule name="Tea Factory" dir=in action=allow protocol=TCP localport=5000
```

**`Error: No database at ...` when running `flask migrate`**
The database does not exist yet. Create it first: `flask --app app init-db --seed`.

**`Database is at schema version N, but this code only knows up to version M`**
The database was migrated by a *newer* copy of the code than the one you are running.
Refusing is deliberate — running old code against a newer schema would corrupt data.
Update the application code, or restore an older backup.

**A schema change had no effect on my existing database**
It was added to `schema.sql`, which only applies to brand-new databases. Add it as a file in
`migrations/` instead — see "Deploying and upgrading".

**The UI looks unstyled, or text is in the wrong font after upgrading**
A stale stylesheet is cached. Hard-reload the page (Ctrl+F5). Older versions pulled fonts
from Google Fonts; they are now self-hosted, so a full reload should leave the page with no
external requests at all.

**`flask --app app run` works but `waitress-serve` says the module cannot be found**
`waitress-serve` resolves `app:app` from the current directory. Run it from the project root,
or use `.venv\Scripts\waitress-serve --host=0.0.0.0 --port=5000 app:app`.
