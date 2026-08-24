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

    # 영문 (미국 주식)
    if query.isalpha():
        return {'code': query.upper(), 'name': query.upper(), 'is_us': True}

    # 6자리 종목코드 직접 입력
    if query.isdigit() and len(query) == 6:
        return {'code': query, 'name': f"종목({query})", 'is_us': False}

    # 한글 종목명 네이버 통합 검색
    try:
        encoded_q = urllib.parse.quote(query)
        url = f"https://m.stock.naver.com/api/search/allList?query={encoded_q}"
        res = requests.get(url, headers=HEADERS, timeout=5)
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
        print(f"Search Error: {e}")

    return {'code': query, 'name': query, 'is_us': False}

@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    clean_code = code.strip().replace('A', '')
    if not clean_code:
        return JSONResponse(status_code=400, content={'error': 'Code is required'})

    try:
        # 네이버 증권 시세 API 직접 조회 (국내/해외 자동 분기)
        if is_us or clean_code.isalpha():
            url = f"https://api.stock.naver.com/stock/{clean_code}/price"
        else:
            url = f"https://m.stock.naver.com/api/stock/{clean_code}/basic"

        res = requests.get(url, headers=HEADERS, timeout=5)

        if res.status_code == 200:
            data = res.json()
            
            # 국내 주식 처리 (closePrice, stockName)
            close_price = data.get('closePrice') or data.get('nowVal')
            stock_name = data.get('stockName') or data.get('stockNameEng') or clean_code
            
            if close_price:
                # 반환 포맷 일치
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
        print(f"Fetch Error: {e}")

    return JSONResponse(status_code=500, content={'error': f'Failed to fetch price for {clean_code}'})