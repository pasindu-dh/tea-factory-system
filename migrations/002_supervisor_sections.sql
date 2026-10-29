-- One supervisor may manage several operational sections.
--
-- users.area could hold only one section per supervisor. supervisor_sections is
-- now the source of truth for assignments; users.area is retained as a legacy
-- mirror of the first assigned section so older queries and exports keep
-- working. The primary key makes duplicate selections impossible at the
-- database level, and ON DELETE CASCADE keeps assignments in step with account
-- deletion.
--
-- Existing supervisors keep their current single section: the INSERT below
-- copies every non-empty users.area value into the new table before any new
-- code reads it. The INSERT is idempotent (INSERT OR IGNORE), so re-running the
-- migration by hand cannot duplicate rows.

CREATE TABLE IF NOT EXISTS supervisor_sections (
  supervisor_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  area          TEXT    NOT NULL CHECK (area IN
                  ('Tea Field A','Tea Field B','Factory Processing','Packaging Section')),
  PRIMARY KEY (supervisor_id, area)
);

CREATE INDEX IF NOT EXISTS idx_supervisor_sections_area
  ON supervisor_sections(area);

INSERT OR IGNORE INTO supervisor_sections (supervisor_id, area)
SELECT user_id, area
  FROM users
 WHERE role = 'supervisor'
   AND area IS NOT NULL
   AND area <> '';
