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
            # 네이버 통합 검색 파싱
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

    # 네이버 차트/시계열 API 호출 (국내주식)
    try:
        url = f'https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=60&requestType=0'
        res = requests.get(url, headers=NAVER_HEADERS, timeout=5)
        
        if res.status_code == 200 and '<item data=' in res.text:
            # XML 차트 데이터 파싱
            import xml.etree.ElementTree as ET
            root = ET.fromstring(res.text)
            items = root.findall('.//item')
            
            price_list = []
            for item in reversed(items):
                data_str = item.attrib.get('data', '')
                parts = data_str.split('|')
                if len(parts) >= 5:
                    price_list.append({
                        'localTradedAt': parts[0],
                        'closePrice': parts[4],
                        'stockName': code
                    })
            
            if price_list:
                return {'ticker': code, 'priceList': price_list}
    except Exception as e:
        print(f'Fetch Price Error: {e}')

    return JSONResponse(status_code=404, content={'error': 'Failed to fetch price data'})