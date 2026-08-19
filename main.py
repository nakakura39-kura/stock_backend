from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

app = FastAPI(
    title="Stock AI Analytics API",
    description="FinanceDataReader 기반 주식 분석 백엔드 API",
    version="1.0.0"
)

# CORS 설정 (모든 도메인 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Stock Analytics Backend is Running"}

# 1. 주식 일봉 데이터 조회 API
@app.get("/api/v1/stock/candles")
def get_stock_candles(
    symbol: str = Query(..., description="종목코드 또는 티커 (예: AAPL, 005930)"),
    timeframe: str = Query("D", description="주기: 'D'(일봉) 또는 'W'(주봉)"),
    days: int = Query(365, description="조회 기간 (일수 단위)")
):
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = fdr.DataReader(symbol, start=start_date)
        
        if df.empty:
            raise HTTPException(status_code=404, detail="해당 종목의 데이터를 찾을 수 없습니다.")
        
        # 주봉 변환 필요한 경우
        if timeframe.upper() == 'W':
            df = df.resample('W').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()

        # 인덱스(날짜) 정리 및 컬럼 소문자 변경
        df = df.reset_index()
        df.rename(columns={
            'Date': 'date', 'Date': 'Date',
            'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'
        }, inplace=True)
        
        # Date 컬럼 문자열 변환
        if 'Date' in df.columns:
            df['date'] = df['Date'].dt.strftime('%Y-%m-%d')
        elif 'index' in df.columns:
            df['date'] = df['index'].dt.strftime('%Y-%m-%d')

        # 필요한 컬럼만 추출
        result_df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
        
        # JSON 변환 (NaN 처리)
        records = json.loads(result_df.to_json(orient='records'))
        return records

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))