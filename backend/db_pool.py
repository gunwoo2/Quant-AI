import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config import settings

_pool: pool.ThreadedConnectionPool = None


def init_pool():
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=settings.DSN
    )
    print("[DB Pool] 초기화 완료 (minconn=2, maxconn=10)")


def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        print("[DB Pool] 전체 연결 종료")


@contextmanager
def get_cursor():
    """커넥션 풀에서 연결을 빌려 커서를 반환하는 컨텍스트 매니저."""
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)