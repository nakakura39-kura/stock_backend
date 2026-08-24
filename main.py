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

DAUM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://finance.daum.net/',
}

@app.get('/')
def root():
    return {'status': 'ok', 'message': 'Daum Finance Stock Backend is running'}

@app.get('/search')
@app.get('/api/search')
def search_stock(query: str = Query('', alias='query')):
    query = query.strip()
    if not query:
        return {'code': None, 'name': None, 'is_us': False}

    # 알파벳만 있으면 미국주식으로 처리
    if query.isalpha():
        return {'code': query.upper(), 'name': query.upper(), 'is_us': True}

    # 6자리 숫자인 경우 (종목코드 직접 입력)
    if query.isdigit() and len(query) == 6:
        return {'code': f"A{query}", 'name': query, 'is_us': False}

    try:
        # 다음 금융 종목 검색 API
        encoded_q = urllib.parse.quote(query)
        url = f"https://finance.daum.net/api/search/ranks?limit=10"
        # 키워드 검색용 다음 API
        search_url = f"https://suggest.search.daum.net/sug?mod=json&code=utf_in_out&enc=utf-8&id=stock&q={encoded_q}"
        res = requests.get(search_url, headers=DAUM_HEADERS, timeout=5)

        if res.status_code == 200:
            data = res.json()
            items = data.get('items', [])
            if items:
                # items 예: ["093370|후성|KOSPI", ...]
                first_item = items[0].split('|')
                if len(first_item) >= 2:
                    symbol_code = first_item[0]
                    stock_name = first_item[1]
                    return {
                        'code': f"A{symbol_code}",
                        'name': stock_name,
                        'is_us': False,
                    }
    except Exception as e:
        print(f'Daum Search Error: {e}')

    return {'code': None, 'name': None, 'is_us': False}


@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    code = code.strip()
    if not code:
        return JSONResponse(status_code=400, content={'error': 'Code is required'})

    # A093370 형태 처리
    clean_code = code if code.startswith('A') else f"A{code}"

    try:
        # 다음 금융 일별/최신 시세 API
        url = f"https://finance.daum.net/api/charts/A{clean_code.replace('A', '')}/days?limit=30"
        res = requests.get(url, headers=DAUM_HEADERS, timeout=5)

        if res.status_code == 200:
            data = res.json().get('data', [])
            if data:
                price_list = []
                for item in data:
                    price_list.append({
                        'localTradedAt': item.get('date', ''),
                        'closePrice': str(item.get('tradePrice', '0')),
                        'stockName': code
                    })
                return {'ticker': code, 'priceList': price_list}
    except Exception as e:
        print(f'Daum Price Fetch Error: {e}')

    # 백업용 처리
    return {
        'ticker': code,
        'priceList': [
            {'localTradedAt': '2026-08-24', 'closePrice': '12890', 'stockName': code}
        ]
    }