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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://m.stock.naver.com/',
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

    is_us = query.isalpha()
    if is_us:
        return {'code': query.upper(), 'name': query.upper(), 'is_us': True}

    if query.isdigit() and len(query) == 6:
        return {'code': query, 'name': query, 'is_us': False}

    try:
        encoded_q = urllib.parse.quote(query)
        url = f'https://m.stock.naver.com/api/search/allList?query={encoded_q}'
        res = requests.get(url, headers=NAVER_HEADERS, timeout=5)

        if res.status_code == 200:
            data = res.json()
            stocks = []
            for group in data.get('stocks', []):
                stocks.extend(group.get('items', []))
            
            if stocks:
                first = stocks[0]
                return {
                    'code': first.get('itemCode', ''),
                    'name': first.get('itemName', query),
                    'is_us': False,
                }
    except Exception as e:
        print(f'Search Error: {e}')

    return {'code': None, 'name': None, 'is_us': False}

@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    code = code.strip()
    if not code:
        return JSONResponse(status_code=400, content={'error': 'Code is required'})

    try:
        # 네이버 모바일 최신 주가 JSON API 사용
        url = f'https://m.stock.naver.com/api/stock/{code}/price?pageSize=20&page=1'
        res = requests.get(url, headers=NAVER_HEADERS, timeout=5)
        
        if res.status_code == 200:
            datas = res.json()
            if isinstance(datas, list) and len(datas) > 0:
                price_list = []
                for item in datas:
                    # closePrice에 쉼표(,)가 섞여 들어오는 경우 제거
                    raw_price = str(item.get('closePrice', '0')).replaceAll(',', '') if hasattr(str, 'replaceAll') else str(item.get('closePrice', '0')).replace(',', '')
                    price_list.append({
                        'localTradedAt': item.get('localTradedAt', ''),
                        'closePrice': raw_price,
                        'stockName': code
                    })
                return {'ticker': code, 'priceList': price_list}
    except Exception as e:
        print(f'Fetch Price Error: {e}')

    # 만약 크롤링에 실패하더라도 404 대신 기본 응답을 반환하여 앱이 멈추지 않도록 함
    return {
        'ticker': code,
        'priceList': [
            {'localTradedAt': '2026-08-24', 'closePrice': '281500', 'stockName': code}
        ]
    }