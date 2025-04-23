# %%
# Imports #

import os

import config_scripts  # noqa: F401
import pandas as pd
import psycopg2
import speedtest
from psycopg2 import pool
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
from src.utils.date_tools import get_current_datetime
from src.utils.display_tools import pprint_df, pprint_ls

# %%
# Variables #

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

dotenv_path = os.path.join(project_root, ".env")
print(dotenv_path)
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

POSTGRES_URL = os.getenv("POSTGRES_URL")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")
POSTGRES_DB = "internet_speed"
POSTGRES_TABLE_NAME = "speedtest_results"


# %%
# Postgres Functions #


def list_all_databases():
    conn = psycopg2.connect(
        host=POSTGRES_URL,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname="postgres",  # connect to the default database
    )
    try:
        cur = conn.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def ensure_database_exists(dbname):
    conn = psycopg2.connect(
        host=POSTGRES_URL,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname="postgres",  # connect to a guaranteed database
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (dbname,))
    exists = cur.fetchone()
    if not exists:
        print(f"Creating database: {dbname}")
        cur.execute(f'CREATE DATABASE "{dbname}";')
    else:
        print(f"Database already exists: {dbname}")
    cur.close()
    conn.close()


# Initialize the connection pool (adjust minconn and maxconn as needed)
POSTGRES_POOL = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=20,  # Limit connections to avoid resource waste
    host=POSTGRES_URL,
    user=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    dbname=POSTGRES_DB,
    port=POSTGRES_PORT,
)


def get_connection():
    """Get a connection from the pool."""
    return POSTGRES_POOL.getconn()


def release_connection(conn):
    """Release a connection back to the pool."""
    POSTGRES_POOL.putconn(conn)


def list_schemas():
    pg_conn = get_connection()
    pg_cursor = pg_conn.cursor()

    try:
        pg_cursor.execute("SELECT schema_name FROM information_schema.schemata;")
        schemas = [row[0] for row in pg_cursor.fetchall()]
        return schemas
    finally:
        pg_cursor.close()
        release_connection(pg_conn)


def list_tables():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE';
        """
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()
        release_connection(conn)


def ensure_table_exists():
    pg_conn = get_connection()
    pg_cursor = pg_conn.cursor()

    # Create authors table
    pg_cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {POSTGRES_TABLE_NAME} (
            timestamp TIMESTAMP WITHOUT TIME ZONE PRIMARY KEY,
            ping_ms REAL,
            download_mbps REAL,
            upload_mbps REAL
        );
        """
    )

    pg_conn.commit()
    pg_cursor.close()
    pg_conn.close()

    print("Tables ensured.")


def insert_speedtest_results(records: list):
    """
    Insert one or more speedtest result dicts into the specified PostgreSQL table.

    Each dict must contain: timestamp, ping_ms, download_mbps, upload_mbps
    """
    print("Logging results:")
    pprint_ls(records, "Results List")

    conn = get_connection()
    cur = conn.cursor()

    try:
        values = [
            (
                rec["timestamp"],
                rec["ping_ms"],
                rec["download_mbps"],
                rec["upload_mbps"],
            )
            for rec in records
        ]

        cur.executemany(
            f"""
            INSERT INTO {POSTGRES_TABLE_NAME} (timestamp, ping_ms, download_mbps, upload_mbps)
            VALUES (%s, %s, %s, %s)
            """,
            values,
        )
        conn.commit()
    finally:
        cur.close()
        release_connection(conn)


def query_speedtest_results_df():
    pg_conn = get_connection()
    pg_cursor = pg_conn.cursor()

    try:
        pg_cursor.execute(
            """
            SELECT timestamp, ping_ms, download_mbps, upload_mbps
            FROM speedtest_results
            ORDER BY timestamp ASC
            """
        )
        rows = pg_cursor.fetchall()
        return pd.DataFrame(
            rows, columns=["timestamp", "ping_ms", "download_mbps", "upload_mbps"]
        )
    finally:
        pg_cursor.close()
        release_connection(pg_conn)


# %%
# New Speedtest #


def get_speedtest_results():
    current_dt = get_current_datetime(format="readable")
    print(f"Running speedtest at {current_dt}")
    num_tries = 3
    for try_num in range(num_tries):
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            ping = round(st.results.ping, 2)
            download = round(st.download() / 1_000_000, 2)  # Convert to Mbps
            upload = round(st.upload() / 1_000_000, 2)  # Convert to Mbps

            print(f"Ping: {ping}, Download: {download}, Upload: {upload}")
            return {
                "timestamp": current_dt,
                "ping_ms": ping,
                "download_mbps": download,
                "upload_mbps": upload,
            }, True
        except Exception as e:
            print(f"Failed to get speedtest results because: {e}")

    print(f"Failed to get speedtest results after {num_tries}")
    return {}, False


# %%
# Main #


def main():
    pprint_ls(list_all_databases(), "List of Databases")

    ensure_database_exists(POSTGRES_DB)

    pprint_ls(list_schemas(), "List of all Schemas in Database")

    pprint_ls(list_tables(), "List of all Tables in Schema")

    ensure_table_exists()

    speedtest_results, success = get_speedtest_results()

    if success:
        insert_speedtest_results([speedtest_results])
    else:
        print("No results because of multiple failures, not logging")

    print("Last 20 Results")
    pprint_df(query_speedtest_results_df().tail(20))


if __name__ == "__main__":
    main()


# %%
