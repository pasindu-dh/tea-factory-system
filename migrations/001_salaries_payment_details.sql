-- Record how a salary line was settled.
--
-- `salaries` already captured who paid it (paid_by) and when (paid_at) but not
-- how, so cash and bank payments could not be told apart when reconciling.
--
-- NULL means "not recorded" (historical rows and any payment made before this
-- column existed), so no NOT NULL and no default: inventing a value for past
-- rows would be a lie. A CHECK constraint is deliberately omitted too — it would
-- require rebuilding the table, which is a much larger migration than this
-- change warrants. Validation happens in the API instead (PAYMENT_METHODS).

ALTER TABLE salaries ADD COLUMN payment_method TEXT;
ALTER TABLE salaries ADD COLUMN payment_ref    TEXT;
