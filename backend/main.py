from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

import db_pool
from routers import stocks, sectors, tickers, market, stock_detail, quant


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 앱 시작 ──
    db_pool.init_pool()
    yield
    # ── 앱 종료 ──
    db_pool.close_pool()


app = FastAPI(
    title="QUANT AI API",
    version="2.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://*.cloudshell.dev",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(stocks.router,  prefix="/api")
app.include_router(sectors.router, prefix="/api")
app.include_router(tickers.router, prefix="/api")
app.include_router(market.router,  prefix="/api")  # 추가
app.include_router(stock_detail.router, prefix="/api")  # 추가
app.include_router(quant.router, prefix="/api")  # 추가


@app.get("/health")
def health_check():
    try:
        with db_pool.get_cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}

########################################################################
# from flask import Flask, jsonify
# from flask_cors import CORS
# import os
# from routes.stock_routes import stock_bp
# from routes.news_routes import news_bp

# def create_app():
#     app = Flask(__name__)
    
#     # 1. CORS 설정
#     CORS(app, supports_credentials=True)

#     # 2. 블루프린트 등록 (모든 API는 /api 접두사를 붙입니다)
#     # stock_routes.py의 @stock_bp.route("/add-ticker-stream/") -> /api/add-ticker-stream/ 가 됨
#     app.register_blueprint(stock_bp, url_prefix='/api')
#     app.register_blueprint(news_bp, url_prefix='/api')

#     # 3. 루트 경로 (헬스체크용)
#     @app.route("/")
#     def index():
#         return jsonify({
#             "status": "Stock API Server is Running",
#             "theme_color": "#D85604"
#         })

#     return app

# # Gunicorn 및 실행용 app 객체 생성
# app = create_app()

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 8080))
#     # debug=True를 넣으면 코드 수정 시 서버가 자동으로 재시작되어 편합니다.
#     app.run(host="0.0.0.0", port=port, debug=True)
    
########################################################################
# from flask import Flask, jsonify
# from flask_cors import CORS
# import os
# from routes.stock_routes import stock_bp
# from routes.news_routes import news_bp  # 만든 파일 임포트
# import services.api_service
# print(f"📍 파이썬이 읽는 api_service 경로: {services.api_service.__file__}")

# def create_app():
#     app = Flask(__name__)
    
#     # 전역 CORS 설정 (필요시)
#     CORS(app, supports_credentials=True)

#     # 1. 루트 경로 (헬스체크용) - 가장 먼저 등록
#     @app.route("/")
#     def index():
#         return jsonify({
#             "status": "Stock API Server is Running",
#             "theme_color": "#D85604"
#         })

#     # 2. 블루프린트 등록
#     app.register_blueprint(stock_bp, url_prefix='/api')
    
#     return app

# # Gunicorn이 찾는 'app' 객체
# app = create_app()
# app.register_blueprint(news_bp)

# if __name__ == "__main__":
#     # 포트 설정 (Cloud Run 기본값 8080)
#     port = int(os.environ.get("PORT", 8080))
#     app.run(host="0.0.0.0", port=port)