import urllib.parse
import requests
import yfinance as yf
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

# 1. 한글/영문 검색어 ➔ 정확한 종목코드/Ticker 변환
@app.get('/search')
@app.get('/api/search')
def search_stock(query: str = Query('', alias='query')):
    q = query.strip()
    if not q:
        return {'code': '005930', 'name': '삼성전자', 'is_us': False}

    # 영문 Ticker (미국 주식)
    if q.isalpha() and len(q) <= 5:
        ticker_symbol = q.upper()
        return {'code': ticker_symbol, 'name': ticker_symbol, 'is_us': True}

    # 6자리 종목코드 (국내 주식)
    if q.isdigit() and len(q) == 6:
        return {'code': q, 'name': f"종목({q})", 'is_us': False}

    # 한글 종목명 네이버 검색
    try:
        encoded_q = urllib.parse.quote(q)
        url = f"https://ac.stock.naver.com/ac?q={encoded_q}&target=stock"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            items = res.json().get('items', [])
            if items and len(items) > 0:
                first = items[0]
                code = first[0]
                name = first[1]
                market = first[2] if len(first) > 2 else ''
                is_us = market.upper() in ['NASDAQ', 'NYSE', 'AMEX']
                return {
                    'code': code,
                    'name': name,
                    'is_us': is_us,
                }
    except Exception as e:
        print(f"Search Error: {e}")

    return {'code': q, 'name': q, 'is_us': False}


# 2. 실시간 주가 데이터 조회 (yfinance 기반)
@app.get('/stock-price')
@app.get('/api/stock-price')
def get_stock_price(
    code: str = Query('', alias='code'), is_us: bool = Query(False, alias='is_us')
):
    clean_code = code.strip().replace('A', '')
    if not clean_code:
        return JSONResponse(status_code=400, content={'error': 'Code is required'})

    try:
        # Ticker 설정
        if is_us or clean_code.isalpha():
            ticker_symbol = clean_code.upper()
        else:
            # 국내 주식 코스피/코스닥 처리 (.KS 우선 조회 후 실패시 .KQ)
            ticker_symbol = f"{clean_code}.KS"

        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period='5d')

        if df.empty and not is_us and not clean_code.isalpha():
            # 코스닥 재시도
            ticker_symbol = f"{clean_code}.KQ"
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period='5d')

        if not df.empty:
            last_price = float(df['Close'].iloc[-1])
            stock_name = clean_code
            try:
                stock_name = ticker.info.get('shortName') or ticker.info.get('longName') or clean_code
            except Exception:
                pass

            return {
                'ticker': clean_code,
                'priceList': [
                    {
                        'localTradedAt': 'today',
                        'closePrice': str(round(last_price, 2)),
                        'stockName': stock_name
                    }
                ]
            }
    except Exception as e:
        print(f"yfinance Fetch Error: {e}")

    return JSONResponse(status_code=500, content={'error': f'Failed to fetch price for {clean_code}'})