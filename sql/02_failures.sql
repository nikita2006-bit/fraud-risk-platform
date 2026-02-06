CREATE TABLE IF NOT EXISTS dq.failures (
    transaction_id TEXT PRIMARY KEY,
    rule_name TEXT,
    details TEXT
)