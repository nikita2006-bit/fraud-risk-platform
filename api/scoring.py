import uuid
import joblib
import numpy as np
import pandas as pd
from psycopg2.extras import RealDictCursor

ART_PATH = "/app/ml/artifacts/fraud_pipeline.pkl"
art = joblib.load(ART_PATH)

lgbm = art["lgbm"]
iso = art["iso"]
lo = float(art["lo"])
hi = float(art["hi"])
w_lgbm = float(art.get("lgbm_weight", 0.85))
w_iso = float(art.get("iso_weight", 0.15))
type_categories = list(art["type_categories"])
feature_cols_lgbm = list(art["feature_cols_lgbm"])
feature_cols_iso = list(art["feature_cols_iso"])

FEATURE_SQL = open("/app/api/features_insert.sql", "r", encoding="utf-8").read()

THR_SQL = """
SELECT
  percentile_cont(0.999) WITHIN GROUP (ORDER BY risk_score) AS block_thr,
  percentile_cont(0.995) WITHIN GROUP (ORDER BY risk_score) AS review_thr
FROM (
  SELECT risk_score
  FROM ml.scores_log
  WHERE status = 'OK' AND risk_score IS NOT NULL
  ORDER BY created_at DESC
  LIMIT %s
) t;
"""

def _prep_type_cats(df: pd.DataFrame) -> pd.DataFrame:
    if "type" in df.columns:
        df["type"] = pd.Categorical(df["type"], categories=type_categories)
    return df

def run_scoring(conn, tx_ids: list[str], ref_window: int = 50000) -> list[str]:
    if not tx_ids:
        return []

    scored_ids: list[str] = []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(FEATURE_SQL, (tx_ids, tx_ids))
        _ = cur.fetchall()

        cur.execute("""
            SELECT *
            FROM ml.ml_features f
            WHERE f.transaction_id = ANY(%s)
              AND NOT EXISTS (
                SELECT 1
                FROM ml.scores_log s
                WHERE s.transaction_id = f.transaction_id
                  AND s.status = 'OK'
              )
        """, (tx_ids,))
        rows = cur.fetchall()
        if not rows:
            return []

        df = pd.DataFrame(rows)

        if "transaction_id" not in df.columns:
            raise RuntimeError("ml.ml_features must include transaction_id")

        df = _prep_type_cats(df)

        missing_lgbm = [c for c in feature_cols_lgbm if c not in df.columns]
        missing_iso = [c for c in feature_cols_iso if c not in df.columns]
        if missing_lgbm:
            raise RuntimeError(f"Missing LGBM feature cols in ml_features: {missing_lgbm[:10]} ...")
        if missing_iso:
            raise RuntimeError(f"Missing ISO feature cols in ml_features: {missing_iso[:10]} ...")

        X_lgbm = df[feature_cols_lgbm].copy()
        X_iso = df[feature_cols_iso].copy()

        lgbm_prob = lgbm.predict_proba(X_lgbm)[:, 1]

        raw = -iso.score_samples(X_iso)
        anom = np.clip((raw - lo) / (hi - lo + 1e-12), 0.0, 1.0)

        final_score = w_lgbm * lgbm_prob + w_iso * anom
        df["final_score"] = final_score

        cur.execute(THR_SQL, (ref_window,))
        thr = cur.fetchone() or {}
        block_thr = thr.get("block_thr")
        review_thr = thr.get("review_thr")

        if block_thr is None or review_thr is None:
            block_thr = float(np.quantile(final_score, 0.999))
            review_thr = float(np.quantile(final_score, 0.995))

        def decide(s: float) -> str:
            if s >= block_thr:
                return "BLOCK"
            if s >= review_thr:
                return "REVIEW"
            return "ALLOW"

        df["decision"] = df["final_score"].apply(decide)

        for r in df.itertuples(index=False):
            req_id = uuid.uuid4().hex
            cur.execute("""
                INSERT INTO ml.scores_log
                  (request_id, status, transaction_id, risk_score, decision)
                VALUES
                  (%s, 'OK', %s, %s, %s)
            """, (req_id, r.transaction_id, float(r.final_score), r.decision))
            scored_ids.append(r.transaction_id)

    return scored_ids