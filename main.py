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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://m.stock.naver.com/'
}

@app.get('/')
def root():
    return {'status': 'ok', 'message': 'Stock Backend API Server'}

@app.get('/search')
@app.get('/api/search')
def search_stock(query: str = Query('', alias='query')):
    query = query.strip()
    if not query:
        return {'code': None, 'name': None, 'is_us': False}

    # 영문 (미국 주식 Ticker)
    if query.isalpha() and len(query) <= 5:
        return {'code': query.upper(), 'name': query.upper(), 'is_us': True}

    # 6자리 종목코드 직접 입력
    if query.isdigit() and len(query) == 6:
        return {'code': query, 'name': f"종목({query})", 'is_us': False}

    # 한글/영문 종목명 ➔ 종목코드 변환 (네이버 자동완성 API)
    try:
        encoded_q = urllib.parse.quote(query)
        url = f"https://ac.stock.naver.com/ac?q={encoded_q}&target=stock"
        res = requests.get(url, headers=HEADERS, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            items = data.get('items', [])
            if items:
                # items[0] 형태: ['000660', 'SK하이닉스', 'KOSPI', ...]
                first_item = items[0]
                code = first_item[0]
                name = first_item[1]
                return {
                    'code': code,
                    'name': name,
                    'is_us': False,
                }
    except Exception as e:
        print(f"Search API Error: {e}")

    return {'code': query, 'name': query, 'is_us': False}


@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    clean_code = code.strip().replace('A', '')
    if not clean_code:
        return JSONResponse(status_code=400, content={'error': 'Code is required'})

    # 숫자가 아닌 종목명이 들어온 경우 에러 응답
    if not is_us and not clean_code.isdigit():
        return JSONResponse(status_code=400, content={'error': f'Invalid code format: {clean_code}'})

    try:
        if is_us:
            url = f"https://api.stock.naver.com/stock/{clean_code}/price"
        else:
            url = f"https://m.stock.naver.com/api/stock/{clean_code}/basic"

        res = requests.get(url, headers=HEADERS, timeout=5)

        if res.status_code == 200:
            data = res.json()
            close_price = data.get('closePrice') or data.get('nowVal')
            stock_name = data.get('stockName') or data.get('stockNameEng') or clean_code
            
            if close_price:
                return {
                    'ticker': clean_code,
                    'priceList': [
                        {
                            'localTradedAt': 'today',
                            'closePrice': str(close_price).replace(',', ''),
                            'stockName': stock_name
                        }
                    ]
                }
    except Exception as e:
        print(f"Price Fetch Exception: {e}")

    return JSONResponse(status_code=500, content={'error': f'Failed to fetch price for {clean_code}'})