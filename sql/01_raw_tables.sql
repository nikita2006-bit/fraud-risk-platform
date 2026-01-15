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
    isflaggedfraud BOOLEAN
)