from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import json
import sys
import os
import traceback
from datetime import datetime, timedelta

# 백엔드 프로젝트 내 samsungAI 경로 자동 탐색
current_dir = os.path.dirname(os.path.abspath(__file__))
samsung_ai_path = os.path.join(current_dir, "samsungAI")

if samsung_ai_path not in sys.path:
    sys.path.append(samsung_ai_path)

if "C:/samsungAI" not in sys.path and os.path.exists("C:/samsungAI"):
    sys.path.append("C:/samsungAI")

analyze_import_error = None
try:
    from service import analyze_stock_for_api
except Exception as e:
    analyze_stock_for_api = None
    analyze_import_error = str(e)

app = FastAPI(
    title="Stock AI Analytics API",
    description="FinanceDataReader 및 samsungAI 기반 주식 분석 백엔드 API",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

KOREA_STOCK_MAP = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "LG에너지솔루션": "373220",
    "삼성바이오로직스": "207940",
    "현대차": "005380",
    "기아": "000270",
    "POSCO홀딩스": "005490",
    "NAVER": "035420",
    "네이버": "035420",
    "카카오": "035720",
    "알테오젠": "196170",
    "에코프로비엠": "247540",
    "에코프로": "086520",
}

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Stock Analytics Backend is Running"}

@app.get("/api/v1/stock/candles")
def get_stock_candles(
    symbol: str = Query(..., description="종목코드 또는 티커"),
    timeframe: str = Query("D", description="주기: 'D'(일봉) 또는 'W'(주봉)"),
    days: int = Query(365, description="조회 기간")
):
    try:
        raw_symbol = symbol.strip()
        target_symbol = KOREA_STOCK_MAP.get(raw_symbol, raw_symbol)
        target_symbol = target_symbol.upper().replace(".KS", "").replace(".KQ", "")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = fdr.DataReader(target_symbol, start=start_date)
        
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail="해당 종목의 데이터를 찾을 수 없습니다.")
        
        if timeframe.upper() == 'W':
            df = df.resample('W').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        elif 'index' in df.columns:
            df['date'] = pd.to_datetime(df['index']).dt.strftime('%Y-%m-%d')

        result_df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        result_df = result_df.fillna(0)
        records = json.loads(result_df.to_json(orient='records'))
        return records

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 조회 실패: {str(e)}")

@app.get("/api/v1/stock/analyze")
def analyze_stock_mtf(
    symbol: str = Query(..., description="종목코드 또는 한글 종목명")
):
    if analyze_stock_for_api is None:
        raise HTTPException(
            status_code=500, 
            detail=f"samsungAI 모듈 로드 실패 (ImportError: {analyze_import_error})"
        )
        
    try:
        raw_symbol = symbol.strip()
        target_symbol = KOREA_STOCK_MAP.get(raw_symbol, raw_symbol)
        target_symbol = target_symbol.upper().replace(".KS", "").replace(".KQ", "")

        result = analyze_stock_for_api(target_symbol)
        
        if isinstance(result, dict) and "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"Error analyzing stock {symbol}:\n{err_msg}")
        raise HTTPException(status_code=500, detail=f"AI 분석 내부 오류: {str(e)}")