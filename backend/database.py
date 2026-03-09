import psycopg2
import os

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "34.67.118.39"),
        database=os.environ.get("DB_NAME", "watchlist"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASS", "rlarjsdn123!")
    )