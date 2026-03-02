CREATE TABLE IF NOT EXISTS ml.scores_log (
    request_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    transaction_id TEXT,
    risk_score NUMERIC,
    decision TEXT,
    error TEXT,
    CONSTRAINT fk_transaction
    FOREIGN KEY (transaction_id) REFERENCES raw.transactions_raw(transaction_id)
);

