from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import requests
import datetime
import json
import numpy as np

app = FastAPI(title="Stock AI Analyzer API")

# CORS 설정 (Flutter 클라이언트 요청 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def fetch_naver_minute_chart(code: str, timeframe: str) -> list:
    """
    네이버 증권 모바일 차트 API를 이용하여 한국 주식 분봉 데이터 수집
    timeframe: 'm15' 또는 'm60'
    """
    # 네이버 API는 분봉을 '15', '60' 등의 숫자로 받음
    tf_map = {'m15': '15', 'm60': '60'}
    tf_str = tf_map.get(timeframe, '15')
    
    # 네이버 모바일 금융 분봉 API 엔드포인트
    url = f"https://m.stock.naver.com/api/item/getTrendList.nhn?code={code}&size=100&time={tf_str}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        result_list = []
        if 'result' in data and data['result']:
            raw_candles = data['result']
            for candle in raw_candles:
                # 네이버 날짜 포맷 예시: '20260827100000'
                dt_str = candle.get('dt', '')
                formatted_time = dt_str
                if len(dt_str) == 14:
                    formatted_time = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]} {dt_str[8:10]}:{dt_str[10:12]}:00"
                
                result_list.append({
                    "time": formatted_time,
                    "open": float(candle.get('ov', 0)),
                    "high": float(candle.get('hv', 0)),
                    "low": float(candle.get('lv', 0)),
                    "close": float(candle.get('cv', 0)),
                    "volume": float(candle.get('aq', 0))
                })
            # 최신순이 0번 인덱스이므로, 차트 그리기 좋게 과거 -> 최신 순으로 정렬 (선택 사항)
            result_list.reverse()
        return result_list
    except Exception as e:
        print(f"네이버 분봉 수집 에러 ({code}, {timeframe}): {e}")
        return []

def fetch_us_minute_chart(code: str, timeframe: str) -> list:
    """
    yfinance를 이용하여 미국 주식 분봉 데이터 수집
    timeframe: 'm15' (15m), 'm60' (60m)
    """
    tf_map = {'m15': '15m', 'm60': '60m'}
    interval = tf_map.get(timeframe, '15m')
    
    try:
        # 분봉은 최대 수집 기간에 제한이 있음 (예: 15m은 최대 60일)
        ticker = yf.Ticker(code)
        df = ticker.history(period="1mo", interval=interval)
        
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
        print(f"US 분봉 수집 에러 ({code}, {timeframe}): {e}")
        return []

def determine_trend(candles: list) -> str:
    """간단한 추세 판별 (최근 5개 캔들의 시가/종가 비교)"""
    if not candles or len(candles) < 5:
        return "-"
    
    recent_closes = [c['close'] for c in candles[-5:]]
    if recent_closes[-1] > recent_closes[0] * 1.005:
        return "상승"
    elif recent_closes[-1] < recent_closes[0] * 0.995:
        return "하락"
    return "보합"

@app.get("/analyze")
async def analyze_stock(
    code: str = Query(..., description="종목 코드 (예: 005930, AAPL)"),
    is_us: bool = Query(False, description="미국 주식 여부"),
    timeframes: str = Query("m15,m60", description="요청할 캔들 분봉 목록 (콤마 분리)")
):
    """
    15분봉, 60분봉 데이터를 수집하고 AI 분석 결과를 모사하여 반환하는 엔드포인트
    """
    tf_list = [tf.strip() for tf in timeframes.split(',') if tf.strip()]
    
    candles_data = {}
    trends_data = {}
    current_price = 0.0
    stock_name = code # 실제 구현 시 이름 조회 로직 필요

    for tf in tf_list:
        if tf not in ['m15', 'm60']:
            continue
            
        if is_us:
            c_data = fetch_us_minute_chart(code, tf)
        else:
            c_data = fetch_naver_minute_chart(code, tf)
            
        candles_data[tf] = c_data[-100:] if c_data else [] # 최근 100개 제한
        trends_data[tf] = determine_trend(c_data)
        
        if c_data and current_price == 0.0:
             current_price = c_data[-1]['close']

    # AI 시나리오 가상 생성 (Flutter에서 에러 안 나도록 규격 유지)
    scenario_path = [0.0, 0.01, -0.005, 0.02, 0.035]
    
    # 최종 응답 JSON 구조 조립
    response_data = {
        "status": "success",
        "code": code,
        "name": stock_name,
        "price": current_price,
        "analysis": {
            "timeframes": {
                "monthly": "-", # 월봉/일봉은 예제 간소화를 위해 하드코딩
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
    
    return response_data