import pandas as pd
import psycopg2
import uuid
from io import StringIO



file = pd.read_csv('PS_20174392719_1491204439457_log.csv')

df = pd.DataFrame(file)
df.insert(0, 
          'transaction_id', 
          [uuid.uuid4().hex for _ in range(len(df))]
          )


print(df.head(5))

conn = psycopg2.connect(
    host='127.0.0.1',
    user='postgres',
    password='postgres',
    port='5433',
    dbname='fraud'
)


sio = StringIO()
df.to_csv(sio, index=False, header=False)

sio.seek(0)

cols = ", ".join(df.columns)

copy_query = f"""
COPY raw.transactions_raw ({cols})
FROM STDIN WITH CSV
"""

copy_to_staging = f"""
COPY raw.transactions_staging ({cols})
FROM STDIN WITH CSV
"""

merge_sql = f"""
INSERT INTO raw.transactions_raw ({cols})
SELECT {cols}
FROM raw.transactions_staging
ON CONFLICT ON CONSTRAINT uq_transaction_natural DO NOTHING
"""


with conn.cursor() as c:
    c.execute("TRUNCATE raw.transactions_staging;")
    c.copy_expert(copy_to_staging, sio)

    c.execute("SELECT COUNT(*) FROM raw.transactions_staging;")
    staged = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM raw.transactions_raw;")
    raw_before = c.fetchone()[0]

    c.execute(merge_sql)

    c.execute("SELECT COUNT(*) FROM raw.transactions_raw;")
    raw_after = c.fetchone()[0]


    conn.commit()

inserted = raw_after - raw_before
duplicates = staged - inserted
print("staged:", staged, "\n",
      "inserded:", inserted, "\n",
      "duplicates: ", duplicates)





