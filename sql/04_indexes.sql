CREATE INDEX IF NOT EXISTS ix_transactions_raw_nameOrig_eventtime
ON raw.transactions_raw (
  nameOrig,
  (TIMESTAMP '2010-01-01' + (step::bigint) * INTERVAL '1 hour')
);
