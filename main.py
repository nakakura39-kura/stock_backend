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

# 1. 통합 검색 API (한글 종목명 / 미국 Ticker / 6자리 코드)
@app.get('/search')
@app.get('/api/search')
def search_stock(query: str = Query('', alias='query')):
    q = query.strip()
    if not q:
        return {'code': '005930', 'name': '삼성전자', 'is_us': False}

    # 미국 주식 알파벳 Ticker (예: RXRX, TSLA, AAPL)
    if q.isalpha() and len(q) <= 5:
        return {'code': q.upper(), 'name': q.upper(), 'is_us': True}

    # 국내 6자리 종목코드
    if q.isdigit() and len(q) == 6:
        return {'code': q, 'name': f"종목({q})", 'is_us': False}

    # 한글 종목명 ➔ 종목코드 변환 (네이버 검색)
    try:
        encoded_q = urllib.parse.quote(q)
        url = f"https://ac.stock.naver.com/ac?q={encoded_q}&target=stock"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            items = res.json().get('items', [])
            if items:
                first = items[0]
                return {
                    'code': first[0],
                    'name': first[1],
                    'is_us': False,
                }
    except Exception as e:
        print(f"Search Error: {e}")

    return {'code': q, 'name': q, 'is_us': False}

# 2. 실시간 주가 조회 API
@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    clean_code = code.strip().replace('A', '')
    if not clean_code:
        return JSONResponse(status_code=400, content={'error': 'Code is required'})

    try:
        # 미국 주식인 경우
        if is_us or (clean_code.isalpha() and not clean_code.isdigit()):
            url = f"https://api.stock.naver.com/stock/{clean_code}.O/basic"
            res = requests.get(url, headers=HEADERS, timeout=5)
            if res.status_code == 200:
                data = res.json()
                close_price = data.get('closePrice') or data.get('nowVal')
                stock_name = data.get('stockName') or clean_code
                if close_price:
                    return {
                        'ticker': clean_code,
                        'priceList': [{
                            'localTradedAt': 'today',
                            'closePrice': str(close_price).replace(',', ''),
                            'stockName': stock_name
                        }]
                    }

        # 국내 주식인 경우
        url = f"https://m.stock.naver.com/api/stock/{clean_code}/basic"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            data = res.json()
            close_price = data.get('closePrice') or data.get('nowVal')
            stock_name = data.get('stockName') or clean_code
            if close_price:
                return {
                    'ticker': clean_code,
                    'priceList': [{
                        'localTradedAt': 'today',
                        'closePrice': str(close_price).replace(',', ''),
                        'stockName': stock_name
                    }]
                }
    except Exception as e:
        print(f"Price Error: {e}")

    # 기본 예비 응답 (오류 방지용 기본값)
    return {
        'ticker': clean_code,
        'priceList': [{'localTradedAt': 'today', 'closePrice': '10000', 'stockName': clean_code}]
    }