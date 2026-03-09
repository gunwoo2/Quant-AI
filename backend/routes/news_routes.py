from flask import Blueprint, jsonify, make_response
from flask_cors import CORS
import requests
from secret_info.config import settings

# 1. Blueprint 정의 및 CORS 설정
news_bp = Blueprint('news', __name__)
CORS(news_bp, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# API 키 설정
NEWS_API_KEY = settings.NEWS_API_KEY
FMP_API_KEY = settings.FMP_API_KEY

# --- 1. 뉴스 가져오기 ---
@news_bp.route('/news/<ticker>', methods=['GET'], strict_slashes=False)
def get_news(ticker):
    url = f"https://newsapi.org/v2/everything?q={ticker}&sortBy=publishedAt&language=en&pageSize=10&apiKey={NEWS_API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        articles = []
        for art in data.get('articles', []):
            articles.append({
                'source': art['source']['name'],
                'time': art['publishedAt'][:10],
                'title': art['title'],
                'content': art['description'],
                'thumbnail': art.get('urlToImage') or 'https://via.placeholder.com/140x90/222/D85604?text=No+Image',
                'url': art['url']
            })
        return jsonify(articles)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# # --- 2. SEC Filings 가져오기 (FMP API) ---
# @news_bp.route('/api/filings/<ticker>', methods=['GET'], strict_slashes=False)
# def get_filings(ticker):
#     url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker}?limit=10&apikey={FMP_API_KEY}"
#     try:
#         response = requests.get(url)
#         data = response.json()
        
#         # [방어 로직] 데이터가 리스트 형태가 아니면 에러를 출력하거나 빈 리스트 반환
#         if not isinstance(data, list):
#             print(f"API Error Response: {data}") # 터미널에서 확인용
#             return jsonify({"error": "Invalid API Response", "details": str(data)}), 400

#         filings = []
#         for item in data:
#             # item이 사전(dict)인지 한 번 더 확인
#             if isinstance(item, dict):
#                 filings.append({
#                     'type': item.get('type'),
#                     'time': item.get('fillingDate', '')[:10],
#                     'title': f"{item.get('type')} Filing - {item.get('symbol')}",
#                     'content': f"SEC Filing for {ticker}. Accepted: {item.get('acceptedDate', '')}",
#                     'url': item.get('finalLink'),
#                     'source': 'SEC EDGAR'
#                 })
#         return jsonify(filings)
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500