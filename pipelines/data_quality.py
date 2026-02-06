import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
from io import StringIO
import numpy as np



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
  FROM raw.transactions_raw
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)
"""

with conn.cursor() as c:
    c.copy_expert(sql, buf_in)

buf_in.seek(0)
df = pd.read_csv(buf_in)
buf_in.close()

m_amount_le_0 = df["amount"] < 0

m_type_null = (
    df["type"].isna() |
    df["type"].astype("string").str.upper().eq("NULL")
)

m_isfraud_not_bool = (
    df["isfraud"].isna()
)

mask = m_amount_le_0 | m_type_null | m_isfraud_not_bool

conditions = [m_amount_le_0, m_type_null, m_isfraud_not_bool]

choices = ["AMOUNT_LE_0", "TYPE_NULL", "ISFRAUD_NOT_BOOL"]

df["rule_name"] = np.select(conditions, choices, default=pd.NA)

df["details"] = np.select(
    conditions,
    [
        "amount=" + df["amount"].astype("string"),
        "type=" + df["type"].astype("string"),
        "isfraud=" + df["isfraud"].astype("string"),
    ],
    default=pd.NA
    )

df_out = df.loc[mask, ["transaction_id", "rule_name", "details"]].copy()

cols = ", ".join(df_out.columns)

buf_out = StringIO()


df_out.to_csv(buf_out, index=False, header=False)

copy_query = f"""
COPY dq.failures ({cols})
FROM STDIN WITH CSV
"""

with conn.cursor() as c:
    buf_out.seek(0)
    c.execute("TRUNCATE dq.failures")
    c.copy_expert(copy_query, buf_out)
    conn.commit()

buf_out.close()

print(df_out.head())