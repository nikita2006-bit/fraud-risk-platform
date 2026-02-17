import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
from io import StringIO
import numpy as np
import lightgbm as lgb
import joblib
from sklearn.metrics import average_precision_score
from sklearn.model_selection import TimeSeriesSplit, train_test_split
from sklearn.ensemble import IsolationForest



ARTIFACT_PATH = "fraud-risk-platform/ml/artifacts/fraud_pipeline.pkl"


load_dotenv()
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("POSTGRES_DB")
)


buf_in = StringIO()
sql = """
COPY (
  SELECT *
  FROM ml.ml_features
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)
"""

with conn.cursor() as c:
    c.copy_expert(sql, buf_in)

buf_in.seek(0)
df = pd.read_csv(buf_in)
buf_in.close()

DROP = ["transaction_id", "account_id", "counterparty_id", "event_time", "isfraud"]
TARGET = "isfraud"

BOOL_MAP = {True:1, False:0, "t":1, "f":0, "true":1, "false":0, "1":1, "0":0}

def to01(s: pd.Series) -> pd.Series:
    out = s.map(BOOL_MAP)
    if out.isna().any():
        bad = s[out.isna()].unique()
        raise ValueError(f"Unexpected boolean values in {s.name}: {bad}")
    return out.astype(np.int8)

def prep_iso(df):
    X = df.drop(columns=DROP + [TARGET], errors="ignore").copy()

    X["type"] = X["type"].astype("string").fillna("UNKNOWN")
    X["type_code"] = X["type"].astype("category").cat.codes
    X = X.drop(columns=["type"])

    for col in ["is_flagged_fraud", "has_history_7d"]:
        if col in X.columns:
            X[col] = to01(X[col]) if X[col].dtype == "object" else X[col].astype(np.int8)

    X["log_amount"] = np.log1p(X["amount"].astype(float))

    num_cols = X.select_dtypes(include=["number"]).columns
    X[num_cols] = X[num_cols].replace([np.inf, -np.inf], np.nan).fillna(0)

    return X


def prep(df):
    y = to01(df[TARGET])

    X = df.drop(columns=DROP+[TARGET]).copy()

    X["type"] = X["type"].astype("string").fillna("UNKNOWN").astype("category")

    for col in ["is_flagged_fraud", "has_history_7d"]:
        if col in X.columns:
            X[col] = to01(X[col]) if X[col].dtype == "object" else X[col].astype(np.int8)

    if "seconds_since_prev_txn" in X.columns:
        X["seconds_since_prev_txn"] = X["seconds_since_prev_txn"].fillna(-1)

    num_cols = X.select_dtypes(include=["number"]).columns
    X[num_cols] = X[num_cols].replace([np.inf, -np.inf], np.nan).fillna(0)

    return X, y

def metrics_at_k(y_true, score, k_list=(0.001, 0.005, 0.01)):
    out = []

    for k in k_list:
        thr = np.percentile(score, 100*(1-k))
        sel = score >= thr

        tp = (y_true[sel] == 1).sum()
        total = sel.sum()
        fraud_total = y_true.sum()

        precision = tp / total if total else 0
        recall = tp / fraud_total if fraud_total else 0
        base = y_true.mean()
        lift = precision / base if base > 0 else 0

        out.append({
            "k_frac": k,
            "threshold": thr,
            "tx_selected": int(total),
            "precision": precision,
            "recall": recall,
            "lift": lift
        })

    return pd.DataFrame(out)


df = df.sort_values("event_time").reset_index(drop=True)

X = df.drop(columns=DROP)
y = df["isfraud"]

trainval, final = train_test_split(df, test_size=0.2, shuffle=False)

X_tv, y_tv = prep(trainval)


tscv = TimeSeriesSplit(n_splits=3)

X_f, y_f = prep(final)
final_model = lgb.LGBMClassifier(
    n_estimators=800,
    learning_rate=0.05,
    num_leaves=64,
    subsample=0.8,
    colsample_bytree=0.8,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)

final_model.fit(X_tv, y_tv, categorical_feature=["type"])

normal_train = trainval[to01(trainval[TARGET]) == 0].copy()
X_iso_train = prep_iso(normal_train)
X_iso_final = prep_iso(final)

iso = IsolationForest(
    n_estimators=300,
    max_samples=200000, 
    random_state=42,
    n_jobs=-1
)

iso.fit(X_iso_train)
raw_train = -iso.score_samples(X_iso_train)
raw_final = -iso.score_samples(X_iso_final)

lo = np.quantile(raw_train, 0.01)
hi = np.quantile(raw_train, 0.99)

anom_final = np.clip((raw_final - lo) / (hi - lo + 1e-12), 0, 1)



p_lgbm = final_model.predict_proba(X_f)[:,1]
final_score = 0.85 * p_lgbm + 0.15 * anom_final

block_thr  = np.percentile(final_score, 99.9)
review_thr = np.percentile(final_score, 99.5)

decision = np.where(final_score >= block_thr, "BLOCK",
            np.where(final_score >= review_thr, "REVIEW", "ALLOW"))


final_scored = final.copy()
final_scored["p_lgbm"] = p_lgbm
final_scored["anom_score"] = anom_final
final_scored["final_score"] = final_score
final_scored["decision"] = decision

df_block = final_scored[final_scored["decision"] == "BLOCK"].sort_values("final_score", ascending=False)
df_review = final_scored[final_scored["decision"] == "REVIEW"].sort_values("final_score", ascending=False)
df_allow = final_scored[final_scored["decision"] == "ALLOW"].sort_values("final_score", ascending=False)

y_true = to01(final_scored["isfraud"])
pr_final = average_precision_score(y_true, final_scored["final_score"])

print(f"FINAL HOLDOUT PR-AUC: {pr_final:.5f}")
k_df = metrics_at_k(
    y_true.values,
    final_scored["final_score"].values,
    k_list=[0.0005, 0.001, 0.005, 0.01]
)
print(k_df)


caught = final_scored[final_scored["decision"].isin(["BLOCK", "REVIEW"])]

final_scored["isfraud01"] = to01(final_scored["isfraud"])
caught["isfraud01"] = to01(caught["isfraud"])
recall_br = caught["isfraud01"].sum() / final_scored["isfraud01"].sum()

print(f"Recall BLOCK+REVIEW: {recall_br:.4f}")

pipeline = {
    "lgbm": final_model,
    "iso": iso,
    "lo": lo,
    "hi": hi,
    "lgbm_weight": 0.85,
    "iso_weight": 0.15,
    "type_categories": X_tv["type"].cat.categories.tolist(),
    "feature_cols_lgbm": X_tv.columns.tolist(),
    "feature_cols_iso": X_iso_train.columns.tolist(),
}

joblib.dump(pipeline, ARTIFACT_PATH)

print(f"Saved pipeline {ARTIFACT_PATH}")