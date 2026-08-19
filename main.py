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

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 주요 한글 종목명 -> 티커 변환 맵
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

# 1. 주식 일봉 데이터 조회 API
@app.get("/api/v1/stock/candles")
def get_stock_candles(
    symbol: str = Query(..., description="종목코드 또는 티커 (예: 005930, AAPL, 삼성전자)"),
    timeframe: str = Query("D", description="주기: 'D'(일봉) 또는 'W'(주봉)"),
    days: int = Query(365, description="조회 기간 (일수 단위)")
):
    try:
        # 입력값 정제
        raw_symbol = symbol.strip()
        
        # 1) 한글 종목명이 검색어로 들어온 경우 변환
        target_symbol = KOREA_STOCK_MAP.get(raw_symbol, raw_symbol)
        
        # 2) '.KS' 나 '.KQ' 가 붙어있으면 제거 (fdr은 6자리 숫자만 지원)
        target_symbol = target_symbol.upper().replace(".KS", "").replace(".KQ", "")

        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # fdr 데이터 불러오기
        df = fdr.DataReader(target_symbol, start=start_date)
        
        if df is None or df.empty:
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

        # 인덱스(날짜) 정리 및 컬럼 소문자 변환
        df = df.reset_index()
        
        # 컬럼명 표준화
        df.columns = [c.lower() for c in df.columns]
        
        # date 컬럼 찾기 (date 또는 index)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        elif 'index' in df.columns:
            df['date'] = pd.to_datetime(df['index']).dt.strftime('%Y-%m-%d')

        # 필요한 컬럼만 선택
        result_df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        
        # NaN / null 값 처리 후 JSON 변환
        result_df = result_df.fillna(0)
        records = json.loads(result_df.to_json(orient='records'))
        return records

    except Exception as e:
        print(f"Error fetching data for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"데이터 조회 실패: {str(e)}")