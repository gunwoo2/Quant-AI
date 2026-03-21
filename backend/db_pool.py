import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from config import settings
import threading

_pool: pool.ThreadedConnectionPool = None
_bg_semaphore = threading.Semaphore(3)   # 백그라운드 동시 수집 최대 3개


def init_pool():
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        dsn=settings.DSN
    )
    print("[DB Pool] 초기화 완료 (minconn=2, maxconn=20)")


def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        print("[DB Pool] 전체 연결 종료")


def get_pool() -> pool.ThreadedConnectionPool:
    """풀 객체 직접 반환 — 배치에서 수동 conn 관리가 필요한 경우 사용
    
    사용법:
        pool = get_pool()
        conn = pool.getconn()
        try:
            cur = conn.cursor()
            ...
            conn.commit()
        finally:
            pool.putconn(conn)
    """
    global _pool
    if _pool is None:
        init_pool()
    return _pool


@contextmanager
def get_cursor():
    """커넥션 풀에서 연결을 빌려 커서를 반환하는 컨텍스트 매니저.
    
    사용법:
        with get_cursor() as cur:
            cur.execute(...)
    """
    p = get_pool()
    conn = p.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


@contextmanager
def bg_throttle():
    """백그라운드 작업 동시 실행 제한 (최대 3개)"""
    _bg_semaphore.acquire()
    try:
        yield
    finally:
        _bg_semaphore.release()
