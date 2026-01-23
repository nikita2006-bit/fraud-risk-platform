CREATE TABLE IF NOT EXISTS raw.transactions_raw (
    transaction_id TEXT PRIMARY KEY,
    step INTEGER,
    type TEXT,
    amount NUMERIC,
    nameOrig TEXT,
    oldbalanceOrg NUMERIC,
    newbalanceOrig NUMERIC,
    nameDest TEXT,
    oldbalanceDest NUMERIC,
    newbalanceDest NUMERIC,
    isFraud BOOLEAN,
    isFlaggedFraud BOOLEAN,
    CONSTRAINT uq_transaction_natural UNIQUE (
        step, type, amount,
        nameOrig, oldbalanceOrg, newbalanceOrig,
        nameDest, oldbalanceDest, newbalanceDest
    )
);

CREATE TABLE IF NOT EXISTS raw.transactions_staging
(LIKE raw.transactions_raw INCLUDING DEFAULTS);
