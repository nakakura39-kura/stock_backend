import urllib.parse
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 백엔드 파이프라인 엔진 불러오기
from backend_pipeline import MultiWindowPatternEngine, generate_3_scenarios_from_kmeans

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://m.stock.naver.com/'
}

# Multi-Window 파이프라인 엔진 초기화 (D+5 프레임, Top 50개 추출)
engine = MultiWindowPatternEngine(forecast_horizon=5, top_k=50)


@app.get('/')
def root():
    return {'status': 'ok', 'message': 'Stock Backend AI Engine Active'}


# 1. 종목 검색 API
@app.get('/search')
@app.get('/api/search')
def search_stock(query: str = Query('', alias='query')):
    q = query.strip()
    if not q:
        return {'code': '005930', 'name': '삼성전자', 'is_us': False}

    if q.isalpha() and len(q) <= 5:
        return {'code': q.upper(), 'name': q.upper(), 'is_us': True}

    if q.isdigit() and len(q) == 6:
        return {'code': q, 'name': f"종목({q})", 'is_us': False}

    try:
        encoded_q = urllib.parse.quote(q)
        url = f"https://ac.stock.naver.com/ac?q={encoded_q}&target=stock"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            items = res.json().get('items', [])
            if items:
                first = items[0]
                code, name = first[0], first[1]
                market = first[2] if len(first) > 2 else ''
                is_us = market.upper() in ['NASDAQ', 'NYSE', 'AMEX']
                return {'code': code, 'name': name, 'is_us': is_us}
    except Exception as e:
        print(f"Search API Error: {e}")

    return {'code': q, 'name': q, 'is_us': False}


# 2. 실시간 주가 + 5년 OHLCV 기반 AI 3개 시나리오 API
@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    clean_code = code.strip().replace('A', '')
    if not clean_code:
        return JSONResponse(status_code=400, content={'error': 'Code is required'})

    # Step 1: 5년치 OHLCV 데이터 수집 (yfinance 기반)
    df_historical = engine.fetch_historical_ohlcv(clean_code, is_us, period="5y")

    # Step 2: Multi-Window (5/10/20/60일) 앙상블 패턴 검색
    if not df_historical.empty:
        current_price = float(df_historical['Close'].iloc[-1])
        stock_name = clean_code

        # Top 50개 과거 사례의 미래 D+1 ~ D+5 수익률 매트릭스 계산
        future_returns_matrix = engine.search_ensemble_patterns(df_historical)
        
        # K-Means 클러스터링 기반 시나리오 A, B, C 생성
        ai_prediction = generate_3_scenarios_from_kmeans(future_returns_matrix)
    else:
        # 데이터 수집 실패 시 기본 예비값
        current_price = 220.0 if is_us else 75000.0
        ai_prediction = generate_3_scenarios_from_kmeans(np.array([]))

    # 프론트엔드 반환 포맷
    return {
        'ticker': clean_code,
        'priceList': [{
            'localTradedAt': 'today',
            'closePrice': str(current_price),
            'stockName': clean_code,
            'isUs': is_us
        }],
        'aiPrediction': ai_prediction
    }