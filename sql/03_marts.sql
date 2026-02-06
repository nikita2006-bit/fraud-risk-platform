CREATE OR REPLACE VIEW mart.mart_daily_stats AS
    WITH rates AS (
        SELECT 
            step / 24 AS txn_date,
            COUNT(*) AS txn_count,
            SUM(CASE WHEN isFraud THEN 1 ELSE 0 END) AS fraud_count
        FROM raw.transactions_raw t
        LEFT JOIN dq.failures f ON t.transaction_id = f.transaction_id
        WHERE f.transaction_id IS NULL
        GROUP BY step / 24
    )
    SELECT 
        txn_date,
        txn_count,
        fraud_count,
        fraud_count * 1.0 / NULLIF(txn_count, 0) AS fraud_rate
    FROM rates;


CREATE OR REPLACE VIEW mart.mart_type_stats AS
    WITH rates AS (
        SELECT 
            type,
            COUNT(*) AS txn_count,
            SUM(CASE WHEN isFraud THEN 1 ELSE 0 END) AS fraud_count,
            SUM(amount) AS total_amount
        FROM raw.transactions_raw t
        LEFT JOIN dq.failures f ON t.transaction_id = f.transaction_id
        WHERE f.transaction_id IS NULL
        GROUP BY type
    )
    SELECT 
        type,
        txn_count,
        fraud_count,
        fraud_count * 1.0 / NULLIF(txn_count, 0) AS fraud_rate
    FROM rates;


CREATE OR REPLACE VIEW mart.mart_account_stats AS
SELECT
  nameOrig AS account_id,
  step,

  COUNT(*) OVER (PARTITION BY nameOrig ORDER BY step
            RANGE BETWEEN 168 PRECEDING AND CURRENT ROW) AS txn_count_7d,

  SUM(CASE WHEN isFraud THEN 1 ELSE 0 END) OVER (PARTITION BY nameOrig ORDER BY step
            RANGE BETWEEN 168 PRECEDING AND CURRENT ROW) AS fraud_count_7d,

  SUM(amount) OVER (PARTITION BY nameOrig ORDER BY step
            RANGE BETWEEN 168 PRECEDING AND CURRENT ROW) AS total_amount_7d

FROM raw.transactions_raw t
    LEFT JOIN dq.failures f ON t.transaction_id = f.transaction_id
        WHERE f.transaction_id IS NULL;