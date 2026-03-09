from database import get_db_connection
from psycopg2.extras import RealDictCursor

def get_stock_header_info(ticker):
    """
    TICKER_HEADER 테이블에서 티커, 회사명, 설명을 가져옵니다.
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 요청하신 ticker, company_name, description 필드 추출
        query = """
            SELECT ticker, company_name as name, description 
            FROM TICKER_HEADER 
            WHERE ticker = %s
        """
        cur.execute(query, (ticker.upper(),))
        result = cur.fetchone()
        
        cur.close()
        return result
    except Exception as e:
        print(f"❌ DB Service Error: {e}")
        return None
    finally:
        if conn: conn.close()