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

with conn.cursor() as c:
    c.copy_expert(copy_query, sio)
    conn.commit()







