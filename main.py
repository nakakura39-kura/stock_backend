# stock_backend/main.py
import urllib.parse
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

NAVER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://m.stock.naver.com/',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}


@app.get('/')
def root():
    return {'status': 'ok', 'message': 'Stock Backend API is running'}


@app.get('/search')
@app.get('/api/search')
def search_stock(query: str = Query('', alias='query')):
    query = query.strip()
    if not query:
        return {'code': None, 'name': None, 'is_us': False}

    # 영문 알파벳만 들어온 경우 미주 티커로 처리
    is_us = query.isalpha()
    if is_us:
        return {'code': query.upper(), 'name': query.upper(), 'is_us': True}

    # 6자리 숫자인 경우 한국 종목코드로 즉시 처리
    if query.isdigit() and len(query) == 6:
        return {'code': query, 'name': query, 'is_us': False}

    try:
        encoded_q = urllib.parse.quote(query)
        url = f'https://m.stock.naver.com/api/json/search/searchListJson.nhn?keyword={encoded_q}'
        res = requests.get(url, headers=NAVER_HEADERS, timeout=5)

        if res.status_code == 200:
            data = res.json()
            result_data = data.get('result', {})
            stocks = result_data.get('stockData', []) or result_data.get('siteData', {}).get('codeCombine', [])
            
            if stocks:
                first_item = stocks[0]
                code = str(first_item.get('code') or first_item.get('cd', ''))
                name = first_item.get('name') or first_item.get('nm', '')
                
                if code:
                    return {
                        'code': code,
                        'name': name or query,
                        'is_us': False,
                    }
    except Exception as e:
        print(f'Search Proxy Error: {e}')

    return {'code': None, 'name': None, 'is_us': False}


@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    code = code.strip()
    if not code:
        return JSONResponse(
            status_code=400, content={'error': 'Code is required'}
        )

    # 해외주식은 다중 티커 시도, 국내주식은 pure 종목코드 사용
    tickers = (
        [f'{code}.O', f'{code}.N', f'{code}.AM'] if is_us else [code]
    )

    for ticker in tickers:
        # 1차 시도: 네이버 모바일 주가 시계열 API
        endpoints = [
            f'https://m.stock.naver.com/api/stock/{ticker}/price?pageSize=120&page=1',
            f'https://m.stock.naver.com/api/stock/{ticker}/trend?pageSize=120&page=1'
        ]

        for url in endpoints:
            try:
                res = requests.get(url, headers=NAVER_HEADERS, timeout=5)

                if res.status_code == 200:
                    raw_data = res.json()
                    price_list = []
                    
                    if isinstance(raw_data, list):
                        price_list = raw_data
                    elif isinstance(raw_data, dict):
                        price_list = (
                            raw_data.get('priceList', []) 
                            or raw_data.get('prices', [])
                            or raw_data.get('result', [])
                        )

                    if price_list:
                        return {'ticker': ticker, 'priceList': price_list}
            except Exception as e:
                print(f'Price Fetch Error ({ticker} - {url}): {e}')

    return JSONResponse(
        status_code=404, content={'error': 'Failed to fetch price data'}
    )


@app.post('/predict')
@app.post('/api/predict')
def predict(data: dict = None):
    data = data or {}
    historical_prices = data.get('historical_prices', [])

    return {
        'confidence': 74.5,
        'is_low_sample': False,
        'sample_count': len(historical_prices),
        'scenarios': [
            {
                'name': '1순위 시나리오 A (상승 지속)',
                'probability': 0.44,
                'path': [1.0, 1.01, 1.02, 1.025, 1.03, 1.04],
            },
            {
                'name': '2순위 시나리오 B (상승 후 조정)',
                'probability': 0.32,
                'path': [1.0, 1.02, 1.01, 1.015, 1.02, 1.025],
            },
            {
                'name': '3순위 시나리오 C (하락 전환)',
                'probability': 0.24,
                'path': [1.0, 0.99, 0.98, 0.975, 0.97, 0.965],
            },
        ],
    }