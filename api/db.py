# api/db.py
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager

load_dotenv()

pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    host=os.getenv("DB_HOST", "fraud-pg"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("POSTGRES_DB", "fraud"),
)

@contextmanager
def get_conn():
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)
