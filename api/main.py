from fastapi import Query, FastAPI, UploadFile, File
from api.db import get_conn
from api.scoring import run_scoring
import pandas as pd
import uuid
import io
from io import StringIO

app = FastAPI()

@app.get("/scores/recent")
def recent_scores(limit: int = Query(default=100, ge=1, le=1000)):
    sql = """
        SELECT *
        FROM ml.scores_log
        ORDER BY created_at DESC
        LIMIT %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {"items": rows}


@app.post("/ingest/csv")
async def ingest(file: UploadFile = File(),
                 score_after: bool = Query(default=False)
                 ):
    contents = await file.read()
    df = pd.read_csv(io.BytesIO(contents))
    df.insert(
        0,
        "transaction_id",
        [uuid.uuid4().hex for _ in range(len(df))]
    )

    cols = list(df.columns)
    cols_sql = ", ".join(cols)

    sio = StringIO()
    df.to_csv(sio, index=False, header=False)
    sio.seek(0)

    copy_to_staging = f"""
        COPY raw.transactions_staging ({cols_sql})
        FROM STDIN WITH (FORMAT CSV)
    """

    merge_sql = f"""
        INSERT INTO raw.transactions_raw ({cols_sql})
        SELECT {cols_sql}
        FROM raw.transactions_staging
        ON CONFLICT ON CONSTRAINT uq_transaction_natural DO NOTHING
    """

    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE raw.transactions_staging;")

                cur.copy_expert(copy_to_staging, sio)

                cur.execute("SELECT COUNT(*) FROM raw.transactions_staging;")
                staged = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM raw.transactions_raw;")
                raw_before = cur.fetchone()[0]

                cur.execute(merge_sql)

                cur.execute("SELECT COUNT(*) FROM raw.transactions_raw;")
                raw_after = cur.fetchone()[0]

                cur.execute("SELECT transaction_id FROM raw.transactions_staging;")
                tx_ids = [r[0] for r in cur.fetchall()]
                scored_ids = run_scoring(conn, tx_ids=tx_ids) if score_after else []
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        await file.close()

    return {
        "staged_rows": staged,
        "raw_before": raw_before,
        "raw_after": raw_after,
        "inserted": raw_after - raw_before,
        "scored_ids": scored_ids,
        "scored_rows": len(scored_ids)
    }

@app.post("/scores/by_ids")
def scores_by_ids(payload: dict):
    ids = payload.get("ids", [])
    if not ids:
        return {"items": []}
    sql = """
      SELECT *
      FROM ml.scores_log
      WHERE transaction_id = ANY(%s)
      ORDER BY created_at DESC
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ids,))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {"items": rows}

@app.get("/scores/history")
def scores_history(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    sql = """
      SELECT *
      FROM ml.scores_log
      ORDER BY created_at DESC
      LIMIT %s OFFSET %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit, offset))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return {"items": rows}