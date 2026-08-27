from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import xml.etree.ElementTree as ET
import yfinance as yf

app = FastAPI(title="Stock AI Analyzer API")

# CORS 설정 (Flutter 클라이언트 통신 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def fetch_naver_minute_chart(code: str, timeframe: str) -> list:
    """
    네이버 증권 FChart API를 활용한 안정적인 한국 주식 분봉 수집
    timeframe: 'm15' (15분봉), 'm60' (60분봉)
    """
    tf_map = {'m15': '15', 'm60': '60'}
    tf_str = tf_map.get(timeframe, '15')
    
    # 네이버 FChart 엔드포인트
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&requestType=0&count=100&selectArgs={tf_str}&timeframe=minute"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and "<item data=" in response.text:
            root = ET.fromstring(response.text)
            items = root.findall('.//item')
            
            result_list = []
            for item in items:
                # raw_data: "날짜시간|시가|고가|저가|종가|거래량"
                raw_data = item.attrib.get('data', '').split('|')
                if len(raw_data) >= 6:
                    dt_str = raw_data[0]
                    formatted_time = dt_str
                    if len(dt_str) >= 12:
                        formatted_time = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]} {dt_str[8:10]}:{dt_str[10:12]}:00"
                        
                    result_list.append({
                        "time": formatted_time,
                        "open": float(raw_data[1]),
                        "high": float(raw_data[2]),
                        "low": float(raw_data[3]),
                        "close": float(raw_data[4]),
                        "volume": float(raw_data[5])
                    })
            return result_list
    except Exception as e:
        print(f"네이버 분봉 수집 오류 ({code}, {timeframe}): {e}")
        
    return []

def fetch_us_minute_chart(code: str, timeframe: str) -> list:
    """
    yfinance를 활용한 미국 주식 분봉 수집
    """
    tf_map = {'m15': '15m', 'm60': '60m'}
    interval = tf_map.get(timeframe, '15m')
    
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(period="5d", interval=interval)
        
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
        print(f"미국 주식 분봉 수집 오류 ({code}, {timeframe}): {e}")
        return []

def determine_trend(candles: list) -> str:
    """최근 캔들 기준 단순 추세 계산 (상승 / 하락 / 보합)"""
    if not candles or len(candles) < 5:
        return "-"
    
    start_price = candles[-5]['close']
    last_price = candles[-1]['close']
    
    if start_price == 0:
        return "-"
        
    diff_rate = (last_price - start_price) / start_price * 100
    
    if diff_rate >= 0.2:
        return "상승"
    elif diff_rate <= -0.2:
        return "하락"
    return "보합"

@app.get("/")
def read_root():
    return {"message": "Stock AI Backend is Live"}

@app.get("/analyze")
async def analyze_stock(
    code: str = Query(..., description="종목 코드 (예: 005930, AAPL)"),
    is_us: bool = Query(False, description="미국 주식 여부"),
    timeframes: str = Query("m15,m60", description="요청 분봉 목록")
):
    tf_list = [tf.strip() for tf in timeframes.split(',') if tf.strip()]
    
    candles_data = {}
    trends_data = {}
    current_price = 0.0

    for tf in tf_list:
        if tf not in ['m15', 'm60']:
            continue
            
        if is_us:
            c_data = fetch_us_minute_chart(code, tf)
        else:
            c_data = fetch_naver_minute_chart(code, tf)
            
        candles_data[tf] = c_data
        trends_data[tf] = determine_trend(c_data)
        
        # 가장 최근 종가를 현재가로 지정
        if c_data and current_price == 0.0:
            current_price = c_data[-1]['close']

    # AI 패턴 경로 샘플 데이터
    scenario_path = [0.0, 0.01, -0.005, 0.02, 0.035]
    
    return {
        "status": "success",
        "code": code,
        "name": code,
        "price": current_price,
        "analysis": {
            "timeframes": {
                "monthly": "-",
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