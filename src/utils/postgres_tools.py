# %%
# Imports #

import os
import socket
import sys

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2 import pool, sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# append grandparent
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.display_tools import pprint_df

# %%
# Variables #

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

dotenv_path = os.path.join(project_root, ".env")
print(dotenv_path)
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

POSTGRES_URL = os.getenv("POSTGRES_URL")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")


# %%
# Connect To Postgres #


def get_pool(postgres_db):
    # Initialize the connection pool (adjust minconn and maxconn as needed)
    postgres_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=20,  # Limit connections to avoid resource waste
        host=POSTGRES_URL,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname=postgres_db,
        port=POSTGRES_PORT,
    )

    return postgres_pool


def get_connection(postgres_pool):
    """Get a connection from the pool."""
    return postgres_pool.getconn()


def release_connection(postgres_pool, conn):
    """Release a connection back to the pool."""
    postgres_pool.putconn(conn)


# %%
# Functions #


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


def query_postgres(postgres_pool, query):
    """Executes a given SQL query and returns a Pandas DataFrame."""
    pg_conn = None
    pg_cursor = None
    try:
        pg_conn = get_connection(postgres_pool)
        pg_cursor = pg_conn.cursor()

        pg_cursor.execute(query)

        if not pg_cursor.description:
            raise ValueError("No data found or invalid query.")

        # Get column names
        columns = [desc[0] for desc in pg_cursor.description]

        # Convert result to DataFrame
        df = pd.DataFrame(pg_cursor.fetchall(), columns=columns)

        return df
    finally:
        if pg_cursor:
            pg_cursor.close()


def ensure_postgres_heartbeat_table(postgres_pool):
    pg_conn = get_connection(postgres_pool)
    pg_cursor = pg_conn.cursor()

    # Create test table
    pg_cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS heartbeat (
            id SERIAL PRIMARY KEY,
            device_hostname TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT 'active',
            date_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    pg_conn.commit()
    pg_cursor.close()
    pg_conn.close()

    print("Tables ensured.")


# %%
# Queries #


def test_ensure_postgres_heartbeat_table(postgres_pool):
    # Ensure the table exists
    ensure_postgres_heartbeat_table(postgres_pool)

    # Query to check if the heartbeat table exists
    query = """
    SELECT to_regclass('public.heartbeat');
    """
    result = query_postgres(postgres_pool, query)

    print(result)

    # Assert that the table exists
    assert result.iloc[0, 0] == "heartbeat", "Heartbeat table does not exist"
    print("Test 1 passed: Heartbeat table exists.")


def test_insert_heartbeat(postgres_pool):
    # Get the hostname of the machine
    hostname = socket.gethostname()

    # Open a connection and cursor
    pg_conn = get_connection(postgres_pool)
    try:
        with pg_conn.cursor() as pg_cursor:
            # Insert a heartbeat entry with SQL, including the hostname
            status = "active"

            query_insert = sql.SQL(
                """
                INSERT INTO heartbeat (device_hostname, message, date_time)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                RETURNING id;
            """
            )
            pg_cursor.execute(query_insert, (hostname, status))

            # Fetch the inserted id
            heartbeat_id = pg_cursor.fetchone()[0]

            # Commit the transaction
            pg_conn.commit()

        # Query to check if the heartbeat was added
        query_check = sql.SQL("SELECT * FROM heartbeat WHERE id = %s;")
        with pg_conn.cursor() as pg_cursor:
            pg_cursor.execute(query_check, (heartbeat_id,))
            result_check = pg_cursor.fetchone()

        # Assert that the inserted heartbeat exists
        assert result_check is not None, "Heartbeat entry not found"
        assert result_check[1] == hostname, "Hostname does not match"
        assert result_check[2] == status, "Status does not match"
        print("Test 2 passed: Heartbeat entry inserted and found.")
    finally:
        release_connection(postgres_pool, pg_conn)


# %%
# Tests #


if __name__ == "__main__":
    postgres_pool = get_pool("postgres")
    test_ensure_postgres_heartbeat_table(postgres_pool)

    # query the heartbeat table
    query = """
    SELECT * FROM heartbeat;
    """

    result = query_postgres(postgres_pool, query)
    pprint_df(result)

    test_insert_heartbeat(postgres_pool)


# %%
