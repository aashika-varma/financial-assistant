import os

import psycopg
from dotenv import load_dotenv


def get_connection() -> psycopg.Connection:
    """Open a PostgreSQL connection using local configuration."""
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from your environment")

    return psycopg.connect(
        database_url,
        connect_timeout=15,
    )