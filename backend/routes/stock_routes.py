"""
/home/gguakim33/stock-app/stock-app/backend/routes/stock_routes.py
Routing 관련 코드. 실 로직은 /home/gguakim33/stock-app/stock-app/backend/services/api_service.py 에서 동작
"""
from flask import Blueprint, Response, request, jsonify, stream_with_context
import os
import psycopg2
import yfinance as yf
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from secret_info.config import settings
import json
from psycopg2.extras import execute_values

from services.api_service import (
    get_stock_realtime_data, 
    get_multiple_realtime_prices, 
    get_financials_data, 
    # get_quant_rating
    get_quant_rating as api_get_quant_rating
)

stock_bp = Blueprint('stock', __name__)

def get_db_connection():
    """
    settings 객체에 담긴 정보를 바탕으로 DB에 연결합니다.
    """
    try:
        # 💡 아래 라인을 추가해서 터미널 로그를 확인해 보세요!
        print(f"DEBUG: Connecting to {settings.DB_HOST} as {settings.DB_USER}")

        # ✅ 'DB_HOST'가 아니라 'settings.DB_HOST'로 호출해야 합니다.
        return psycopg2.connect(
            host=settings.DB_HOST,      # 수정됨
            database=settings.DB_NAME,  # 수정됨
            user=settings.DB_USER,      # 수정됨
            password=settings.DB_PASS,  # 수정됨
            connect_timeout=5
        )
    except Exception as e:
        print(f"🚨 DB 연결 실패: {e}")
        raise e

# 섹터 매핑 (기존 유지)
SECTOR_MAP = {
    "Technology": "it",
    "Financial Services": "financials",
    "Healthcare": "healthcare",
    "Consumer Cyclical": "discretionary",
    "Communication Services": "comm",
    "Industrials": "industrials",
    "Energy": "energy",
    "Consumer Defensive": "staples",
    "Real Estate": "realestate",
    "Utilities": "utilities",
    "Basic Materials": "materials"
}


@stock_bp.route("/add-ticker-stream/", methods=["POST"])
def add_ticker_stream():
    # 1. 데이터를 generate 밖에서 먼저 확보
    data = request.get_json() 
    if not data:
        return jsonify({"error": "No data provided"}), 400

    ticker = data.get("ticker", "").strip().upper()
    raw_user_sector = data.get("sector") or data.get("sector_id")
    
    # 섹터 기본 처리
    if isinstance(raw_user_sector, dict):
        user_sector = raw_user_sector.get('id', 'it')
    else:
        user_sector = str(raw_user_sector) if raw_user_sector else "it"
    if "object" in user_sector.lower(): user_sector = "it"
    country = data.get("country") or "US"

    def generate():
        def send_log(msg, status="running"):
            return f"data: {json.dumps({'message': msg, 'status': status})}\n\n"

        conn = None
        cur = None
        try:
            # 2. DB 연결 및 중복 체크
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT ticker FROM TICKER_HEADER WHERE ticker = %s", (ticker,))
            if cur.fetchone():
                yield send_log(f"⚠️ 이미 등록된 티커입니다: {ticker}", status="error")
                return

            yield send_log(f"🚀 {ticker} 분석을 시작합니다...")
            
            # 3. Yahoo Finance 정보 가져오기
            stock = yf.Ticker(ticker)
            info = stock.info
            
            if not info or 'longName' not in info:
                yield send_log(f"❌ 유효하지 않은 티커입니다: {ticker}", status="error")
                return

            company_name = info.get('longName', ticker)
            yf_sector_name = info.get('sector', '')
            
            try:
                final_sector = SECTOR_MAP.get(yf_sector_name, user_sector)
            except NameError:
                final_sector = yf_sector_name if yf_sector_name else user_sector

            # 4. Header 저장
            yield send_log(f"📝 기업 프로필 저장 중: {company_name}")
            header_sql = """
                INSERT INTO TICKER_HEADER 
                (ticker, company_name, sector, industry, exchange, created_at, description, country) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) 
                ON CONFLICT (ticker) DO NOTHING;
            """
            cur.execute(header_sql, (
                ticker, company_name, final_sector, info.get('industry', 'N/A'),
                info.get('exchange', 'N/A'), datetime.now().strftime('%Y-%m-%d'), 
                info.get('longBusinessSummary', '')[:3000], country
            ))
            conn.commit()

            # 5. 3년치 시세 데이터 수집 및 저장
            yield send_log(f"📊 {ticker} 3년치 호가정보 수집 중...")
            hist = stock.history(period="3y")
            
            if not hist.empty:
                data_list = [
                    (
                        ticker, 
                        date.date(),
                        float(row['Open']), 
                        float(row['High']), 
                        float(row['Low']), 
                        float(row['Close']),
                        int(row['Volume'])
                    ) for date, row in hist.iterrows()
                ]
                
                yield send_log(f"💾 {len(data_list)}개의 데이터를 DB에 고속 저장 중...")
                
                item_sql = """
                    INSERT INTO ticker_item (
                        ticker, trading_date, open_price, high_price, low_price, close_price, volume
                    ) VALUES %s
                    ON CONFLICT (ticker, trading_date) DO UPDATE SET 
                        close_price = EXCLUDED.close_price,
                        volume = EXCLUDED.volume;
                """
                execute_values(cur, item_sql, data_list)
                conn.commit()
                
                yield send_log(f"✅ {ticker} 저장 완료!", status="success")
            else:
                yield send_log(f"⚠️ 시세 데이터가 없습니다.", status="success")

        except Exception as e:
            if conn: conn.rollback()
            print(f"Error detail: {str(e)}")
            yield send_log(f"❌ 오류 발생: {str(e)}", status="error")

        finally:
            if cur: cur.close()
            if conn: conn.close()

    # ✅ 이 return 문이 generate 함수 밖, add_ticker_stream 함수 바로 안에 있어야 합니다!
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# 2. 섹터 목록 조회
@stock_bp.route("/sectors", methods=["GET"])
def get_sectors():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT SECTOR, SECTOR_DESC FROM SECTOR_DROPBOX ORDER BY SECTOR_DESC ASC")
        rows = cur.fetchall()
        # 프론트엔드 형식에 맞춰 반환
        return jsonify([{"id": r[0], "ko": r[1]} for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

# 3. 주식 리스트 조회 (메인 페이지용)
@stock_bp.route("/stocks", methods=["GET"])
def get_stocks():
    sector_param = request.args.get("sector", "all").lower()
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT 
                h.ticker, 
                h.company_name, 
                h.country, 
                h.sector,
                -- quant_rank(1~7) 값을 등급(S~D)으로 치환
                CASE 
                    WHEN q.quant_rank = 1 THEN 'S'
                    WHEN q.quant_rank = 2 THEN 'A+'
                    WHEN q.quant_rank = 3 THEN 'A'
                    WHEN q.quant_rank = 4 THEN 'B+'
                    WHEN q.quant_rank = 5 THEN 'B'
                    WHEN q.quant_rank = 6 THEN 'C'
                    WHEN q.quant_rank = 7 THEN 'D'
                    ELSE 'N/A'
                END AS final_grade,
                q.trading_date
            FROM ticker_header h
            LEFT JOIN (
                -- 최신 날짜의 데이터만 추출하기 위한 서브쿼리
                SELECT DISTINCT ON (ticker) 
                    ticker, 
                    quant_rank, 
                    trading_date
                FROM stock_quant_analysis
                ORDER BY ticker, trading_date DESC
            ) q ON h.ticker = q.ticker;
        """
        if sector_param != "all":
            query += " WHERE LOWER(h.sector) = %s"
            cur.execute(query, (sector_param,))
        else:
            cur.execute(query)

        stocks = cur.fetchall()
        if not stocks: return jsonify([])

        ticker_list = [s["ticker"].upper() for s in stocks]
        
        # ✅ api_service의 통합 함수 호출 (KIS + Yahoo fallback 자동 처리)
        realtime_data = get_multiple_realtime_prices(ticker_list)

        result = []
        for s in stocks:
            ticker = s["ticker"].upper()
            price_info = realtime_data.get(ticker, {})
            result.append({
                **s,
                "price": round(price_info.get("price", 0), 2),
                "change": round(price_info.get("change", 0), 2)
            })
        return jsonify(result)
    except Exception as e:
        print(f"🚨 GET_STOCKS ERROR: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

# 4. 주식 상세 정보 (상세 페이지용)
@stock_bp.route("/stock/detail/<ticker>", methods=['GET'])
def get_stock_detail(ticker):
    conn = None
    cur = None
    try:
        ticker = ticker.upper()
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT ticker, company_name as name, description, country, sector, industry, exchange 
            FROM TICKER_HEADER WHERE ticker = %s
        """, (ticker,))
        db_data = cur.fetchone()
        if not db_data: return jsonify({"error": "종목 없음"}), 404

        # ✅ 상세 지표까지 계산된 데이터 호출
        detail_info = get_stock_realtime_data(ticker)

        return jsonify({
            "header": {
                **db_data,
                "logo": f"https://financialmodelingprep.com/image-stock/{ticker}.png"
            },
            "realtime": detail_info
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()

# 5. 과거 데이터 (차트용)
@stock_bp.route("/stock/history/<ticker>", methods=['GET'])
def get_stock_history_from_db(ticker):
    conn = None
    try:
        ticker = ticker.upper()
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        frequency = request.args.get('frequency', '1d')

        if not start_date or start_date == 'undefined':
            start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        if not end_date or end_date == 'undefined':
            end_date = datetime.now().strftime('%Y-%m-%d')

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        trunc_unit = 'day'
        if frequency == '1wk': trunc_unit = 'week'
        elif frequency == '1mo': trunc_unit = 'month'

        query = f"""
            SELECT 
                TO_CHAR(DATE_TRUNC('{trunc_unit}', trading_date), 'YYYY-MM-DD') as trading_date,
                AVG(open_price) as open_price, AVG(close_price) as close_price,
                SUM(volume) as volume, AVG(per) as per, AVG(roic) as roic
            FROM ticker_item
            WHERE ticker = %s AND trading_date BETWEEN %s AND %s
            GROUP BY DATE_TRUNC('{trunc_unit}', trading_date)
            ORDER BY trading_date DESC;
        """
        cur.execute(query, (ticker, start_date, end_date))
        return jsonify(cur.fetchall()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

# 6. 재무제표 및 퀀트 레이팅
@stock_bp.route("/stock/detail/<ticker>/financials", methods=['GET'])
def get_stock_financials(ticker):
    period = request.args.get('period', 'annual')
    return jsonify(get_financials_data(ticker.upper(), period))

@stock_bp.route("/stock/detail/<ticker>/quant", methods=['GET'])
def get_stock_quant_rating(ticker):
    print(f"🚀 [DEBUG] Quant API Route Hit! Ticker: {ticker}") # 이모지를 넣어 찾기 쉽게 함
    
    # api_service에서 가져온 함수를 호출합니다.
    result = api_get_quant_rating(ticker.upper())
    
    return jsonify(result)