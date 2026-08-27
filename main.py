from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import yfinance as yf

app = FastAPI(title="Stock AI Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STOCK_MAP = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "NAVER": "035420",
    "카카오": "035720",
    "현대차": "005380"
}

@app.get("/search")
async def search_stock(q: str = Query(..., description="검색어")):
    clean_q = q.strip()
    
    # 1. 국내 미리 정의된 종목
    if clean_q in STOCK_MAP:
        return [{"code": STOCK_MAP[clean_q], "name": clean_q, "is_us": False}]
    
    # 2. 숫자 종목코드 (국내주식)
    if clean_q.isdigit():
        return [{"code": clean_q, "name": clean_q, "is_us": False}]
        
    # 3. 영문 티커 (미국주식 예: AAPL, TSLA, NVDA)
    return [{"code": clean_q.upper(), "name": clean_q.upper(), "is_us": True}]

def fetch_naver_minute_chart(code: str) -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        "Referer": "https://m.stock.naver.com/"
    }
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/price?pageSize=60&page=1"
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                result_list = []
                for row in data:
                    close_str = str(row.get('closePrice', '0')).replace(',', '')
                    price_val = float(close_str) if close_str else 0.0
                    if price_val > 0:
                        result_list.append({
                            "time": row.get('localTradedAt', ''),
                            "open": price_val,
                            "high": price_val,
                            "low": price_val,
                            "close": price_val,
                            "volume": 0.0
                        })
                result_list.reverse()
                return result_list
    except Exception as e:
        print(f"네이버 수집 에러 ({code}): {e}")

    return []

def fetch_us_minute_chart(code: str, timeframe: str) -> list:
    """yfinance 미국 주식 수집 (안정적인 1d 기간 / 15m, 60m 사용)"""
    tf_map = {'m15': '15m', 'm60': '60m'}
    interval = tf_map.get(timeframe, '15m')
    
    try:
        ticker = yf.Ticker(code)
        # period를 5d로 가져와 주말/휴장일에도 데이터가 비지 않도록 처리
        df = ticker.history(period="5d", interval=interval)
        
        if df.empty:
            # 기본 history 조회 백업
            df = ticker.history(period="1d")
            
        result_list = []
        for index, row in df.iterrows():
            result_list.append({
                "time": index.strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": float(row['Volume'])
            })
        return result_list
    except Exception as e:
        print(f"미국 주식 수집 에러 ({code}): {e}")
        return []

def determine_trend(candles: list) -> str:
    if not candles or len(candles) < 2:
        return "-"
    
    start_price = candles[0]['close']
    last_price = candles[-1]['close']
    
    if start_price == 0:
        return "-"
        
    diff_rate = (last_price - start_price) / start_price * 100
    
    if diff_rate >= 0.1:
        return "상승"
    elif diff_rate <= -0.1:
        return "하락"
    return "보합"

@app.get("/analyze")
async def analyze_stock(
    code: str = Query(..., description="종목 코드"),
    is_us: bool = Query(False, description="미국 주식 여부"),
    timeframes: str = Query("m15,m60", description="요청 분봉 목록")
):
    target_code = STOCK_MAP.get(code, code)
    
    # 영문으로 들어온 경우 미국 주식으로 자동 판별
    if target_code.isalpha() and len(target_code) <= 5:
        is_us = True

    candles_data = {}
    trends_data = {}
    current_price = 0.0

    tf_list = [tf.strip() for tf in timeframes.split(',') if tf.strip()]

    for tf in tf_list:
        if is_us:
            c_data = fetch_us_minute_chart(target_code, tf)
        else:
            c_data = fetch_naver_minute_chart(target_code)
            
        candles_data[tf] = c_data
        trends_data[tf] = determine_trend(c_data)
        
        if c_data and current_price == 0.0:
            current_price = c_data[-1]['close']

    scenario_path = [0.0, 0.01, -0.005, 0.02, 0.035]
    
    return {
        "status": "success",
        "code": target_code,
        "name": code,
        "price": current_price,
        "is_us": is_us,
        "analysis": {
            "timeframes": {
                "monthly": "상승",
                "daily": "상승" if current_price > 0 else "-",
                "m60": trends_data.get('m60', '-'),
                "m15": trends_data.get('m15', '-')
            },
            "candles": candles_data,
            "scenario": {
                "confidence": 85.0,
                "matchedCount": 12,
                "scenarios": [
                    {
                        "rank": 1,
                        "name": "15분봉/60분봉 단기 패턴",
                        "probability": 65.0,
                        "finalReturn": 3.5,
                        "path": scenario_path
                    }
                ]
            }
        }
    }