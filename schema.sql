-- Tea Factory System schema (SQLite)
-- Dates are ISO 'YYYY-MM-DD' TEXT, times 'HH:MM', money integer rupees.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  user_id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name                 TEXT    NOT NULL,
  role                 TEXT    NOT NULL CHECK (role IN ('owner','supervisor','servant')),
  gender               TEXT    NOT NULL CHECK (gender IN ('Male','Female')),
  phone                TEXT    NOT NULL UNIQUE,
  password_hash        TEXT    NOT NULL,
  work_type            TEXT    CHECK (work_type IN ('Tea Collector','Retail Worker')),
  area                 TEXT,
  is_active            INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0,1)),
  created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
  CHECK ((role = 'servant' AND work_type IN ('Tea Collector','Retail Worker'))
      OR (role <> 'servant' AND work_type IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role, is_active);

CREATE TABLE IF NOT EXISTS attendance (
  attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
  servant_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  work_date     TEXT    NOT NULL,
  check_in      TEXT,
  check_out     TEXT,
  status        TEXT    NOT NULL CHECK (status IN ('Present','Absent')) DEFAULT 'Absent',
  recorded_by   INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  updated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (servant_id, work_date)
);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(work_date);
CREATE INDEX IF NOT EXISTS idx_attendance_servant_date ON attendance(servant_id, work_date);

-- Several bags may be weighed for one servant on the same day: no uniqueness here.
CREATE TABLE IF NOT EXISTS weights (
  weight_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  servant_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  work_date       TEXT    NOT NULL,
  original_weight REAL    NOT NULL CHECK (original_weight > 0),
  adjusted_weight REAL    NOT NULL CHECK (adjusted_weight >= 0),
  rainy_day       INTEGER NOT NULL DEFAULT 0 CHECK (rainy_day IN (0,1)),
  area            TEXT    NOT NULL CHECK (area IN
                    ('Tea Field A','Tea Field B','Factory Processing','Packaging Section')),
  recorded_by     INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_weights_date ON weights(work_date);
CREATE INDEX IF NOT EXISTS idx_weights_servant_date ON weights(servant_id, work_date);

CREATE TABLE IF NOT EXISTS work_area_assignments (
  assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
  servant_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  work_date     TEXT    NOT NULL,
  area          TEXT    NOT NULL CHECK (area IN
                  ('Tea Field A','Tea Field B','Factory Processing','Packaging Section')),
  assigned_by   INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (servant_id, work_date)
);
CREATE INDEX IF NOT EXISTS idx_assignments_date ON work_area_assignments(work_date);

CREATE TABLE IF NOT EXISTS rate_config (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  above_80      REAL NOT NULL CHECK (above_80 > 0),
  between_70_80 REAL NOT NULL CHECK (between_70_80 > 0),
  below_70      REAL NOT NULL CHECK (below_70 > 0),
  male_daily    REAL NOT NULL CHECK (male_daily > 0),
  female_daily  REAL NOT NULL CHECK (female_daily > 0),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_by    INTEGER REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS payroll_runs (
  run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  period_start TEXT    NOT NULL,
  period_end   TEXT    NOT NULL,
  period_days  INTEGER NOT NULL CHECK (period_days = 10),
  status       TEXT    NOT NULL CHECK (status IN ('draft','finalized')) DEFAULT 'draft',
  rates_json   TEXT    NOT NULL,
  compiled_by  INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  compiled_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  finalized_at TEXT,
  UNIQUE (period_start, period_end),
  CHECK (period_end >= period_start)
);

-- One row per servant per run = the payslip.
CREATE TABLE IF NOT EXISTS salaries (
  salary_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        INTEGER NOT NULL REFERENCES payroll_runs(run_id) ON DELETE CASCADE,
  servant_id    INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  work_type     TEXT    NOT NULL,
  present_days  INTEGER NOT NULL,
  period_days   INTEGER NOT NULL,
  attendance_pct INTEGER NOT NULL,
  total_weight  REAL    NOT NULL DEFAULT 0,
  applied_rate  REAL    NOT NULL,
  rate_label    TEXT    NOT NULL,
  total_salary  INTEGER NOT NULL,
  status        TEXT    NOT NULL CHECK (status IN ('Pending','Paid')) DEFAULT 'Pending',
  paid_at       TEXT,
  paid_by       INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  UNIQUE (run_id, servant_id)
);
CREATE INDEX IF NOT EXISTS idx_salaries_servant ON salaries(servant_id, status);
