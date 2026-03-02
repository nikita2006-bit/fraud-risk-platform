WITH new_tx AS (
  SELECT transaction_id, step, "type", amount, nameOrig, nameDest, isFraud, isFlaggedFraud,
         oldbalanceOrg, newbalanceOrig, oldbalanceDest, newbalanceDest
  FROM raw.transactions_raw
  WHERE transaction_id = ANY(%s)
),
bounds AS (
  SELECT MIN(step) AS min_step FROM new_tx
),
scope AS (
  SELECT t.* 
  FROM raw.transactions_raw t
  WHERE (
      t.nameOrig IN (SELECT DISTINCT nameOrig FROM new_tx)
      OR t.nameDest IN (SELECT DISTINCT nameDest FROM new_tx)
  )
  AND t.step >= (SELECT min_step FROM bounds) - 168
),
tx AS (
  SELECT
    transaction_id,
    step,
    nameOrig AS account_id,
    nameDest AS counterparty_id,
    amount,
    "type" AS type,
    isFraud AS isfraud,
    isFlaggedFraud AS is_flagged_fraud,
    oldbalanceOrg,
    newbalanceOrig,
    oldbalanceDest,
    newbalanceDest,
    TIMESTAMP '2010-01-01' + (step::bigint) * INTERVAL '1 hour' AS event_time
  FROM scope
),
lagged AS (
  SELECT
    *,
    EXTRACT(EPOCH FROM (event_time - LAG(event_time) OVER (
      PARTITION BY account_id ORDER BY event_time
    ))) AS seconds_since_prev_txn
  FROM tx
),
feat AS (
  SELECT
    transaction_id,
    account_id,
    counterparty_id,
    amount,
    event_time,
    type,
    isfraud,
    is_flagged_fraud,
    COUNT(*)      OVER w_1h  AS txn_count_1h,
    COUNT(*)      OVER w_24h AS txn_count_24h,
    COUNT(*)      OVER w_7d  AS txn_count_7d,
    SUM(amount)   OVER w_24h AS sum_amount_24h,
    SUM(amount)   OVER w_7d  AS sum_amount_7d,
    COUNT(*)      OVER w_10m AS velocity_10m,
    SUM((type = 'CASH_OUT')::int)  OVER w_7d AS cash_out_cnt_7d,
    SUM((type = 'TRANSFER')::int)  OVER w_7d AS transfer_cnt_7d,
    AVG(amount)       OVER w_24h AS avg_amount_24h,
    STDDEV_POP(amount) OVER w_7d AS std_amount_7d,
    MAX(amount)       OVER w_7d  AS max_amount_7d,
    seconds_since_prev_txn,
    COUNT(*) OVER (
      PARTITION BY account_id, counterparty_id
      ORDER BY event_time
      RANGE BETWEEN INTERVAL '7 day' PRECEDING AND CURRENT ROW
    ) AS pair_txn_cnt_7d,
    COUNT(*) OVER (
      PARTITION BY counterparty_id
      ORDER BY event_time
      RANGE BETWEEN INTERVAL '7 day' PRECEDING AND CURRENT ROW
    ) AS dest_incoming_cnt_7d
  FROM lagged
  WINDOW
    w_10m AS (PARTITION BY account_id ORDER BY event_time RANGE BETWEEN INTERVAL '10 minute' PRECEDING AND CURRENT ROW),
    w_1h  AS (PARTITION BY account_id ORDER BY event_time RANGE BETWEEN INTERVAL '1 hour'   PRECEDING AND CURRENT ROW),
    w_24h AS (PARTITION BY account_id ORDER BY event_time RANGE BETWEEN INTERVAL '24 hour'  PRECEDING AND CURRENT ROW),
    w_7d  AS (PARTITION BY account_id ORDER BY event_time RANGE BETWEEN INTERVAL '7 day'    PRECEDING AND CURRENT ROW)
),
feat_plus AS (
  SELECT
    f.*,
    CASE
      WHEN f.std_amount_7d IS NULL OR f.std_amount_7d = 0 THEN 0
      ELSE (f.amount - f.avg_amount_24h) / f.std_amount_7d
    END AS amount_zscore_7d,
    f.amount / NULLIF(f.sum_amount_24h, 0) AS amount_to_sum_24h_ratio
  FROM feat f
)
INSERT INTO ml.ml_features (
  transaction_id, account_id, counterparty_id, amount, type, event_time,
  isfraud, is_flagged_fraud,
  txn_count_1h, txn_count_24h, txn_count_7d,
  sum_amount_24h, sum_amount_7d, velocity_10m,
  cash_out_ratio_7d, transfer_ratio_7d,
  seconds_since_prev_txn, avg_amount_24h, std_amount_7d, max_amount_7d,
  amount_zscore_7d, amount_to_sum_24h_ratio,
  pair_txn_cnt_7d, dest_incoming_cnt_7d
)
SELECT
  transaction_id, account_id, counterparty_id, amount, type, event_time,
  isfraud, is_flagged_fraud,
  txn_count_1h, txn_count_24h, txn_count_7d,
  sum_amount_24h, sum_amount_7d, velocity_10m,
  cash_out_cnt_7d::float / NULLIF(txn_count_7d, 0) AS cash_out_ratio_7d,
  transfer_cnt_7d::float / NULLIF(txn_count_7d, 0) AS transfer_ratio_7d,
  seconds_since_prev_txn, avg_amount_24h, std_amount_7d, max_amount_7d,
  amount_zscore_7d, amount_to_sum_24h_ratio,
  pair_txn_cnt_7d, dest_incoming_cnt_7d
FROM feat_plus
WHERE transaction_id = ANY(%s)
ON CONFLICT (transaction_id) DO NOTHING
RETURNING transaction_id;