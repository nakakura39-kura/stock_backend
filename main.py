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

# 한국 주식 종목명-코드 매핑용 네이버 검색 API
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
}

@app.get('/')
def root():
    return {'status': 'ok', 'message': 'Stock API Server with yfinance'}

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

    # 한글 종목명 검색 (네이버 검색 API 활용)
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
        # yfinance 티커 설정 (.KS = 코스피/코스닥 표준)
        ticker_symbol = clean_code if is_us else (f"{clean_code}.KS" if len(clean_code) == 6 else clean_code)
        
        ticker = yf.Ticker(ticker_symbol)
        # 최근 1개월 일별 데이터 가져오기
        df = ticker.history(period="1mo")
        
        # KOSPI에 없으면 KOSDAQ(.KQ) 시도
        if df.empty and not is_us and len(clean_code) == 6:
            ticker_symbol = f"{clean_code}.KQ"
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(period="1mo")

        if not df.empty:
            price_list = []
            # 최근 날짜순 정렬
            df_reversed = df.iloc[::-1]
            for date, row in df_reversed.iterrows():
                price_list.append({
                    'localTradedAt': date.strftime('%Y-%m-%d'),
                    'closePrice': str(int(row['Close'])),
                    'stockName': clean_code
                })
            return {'ticker': clean_code, 'priceList': price_list}

    except Exception as e:
        print(f"yfinance Fetch Error: {e}")

    return JSONResponse(status_code=500, content={'error': 'Failed to fetch price'})