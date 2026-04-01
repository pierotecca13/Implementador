"""Creates and returns a MySQL connection using credentials from .env."""
import os
import mysql.connector
from mysql.connector import MySQLConnection
from dotenv import load_dotenv

load_dotenv()


def get_connection() -> MySQLConnection:
    """Return an open MySQL connection. Caller is responsible for closing it."""
    required = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Check your .env file."
        )

    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        charset="utf8mb4",
        autocommit=False,   # transactions managed by the application layer
    )
