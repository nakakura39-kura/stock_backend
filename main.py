from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

app = FastAPI(
    title="Stock AI Analytics API",
    description="FinanceDataReader 기반 주식 일봉/주봉 분석 백엔드 API",
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


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Stock Analytics Backend is Running"}


# 1. 주식 일봉 / 주봉 데이터 조회 API
@app.get("/api/v1/stock/candles")
def get_stock_candles(
    symbol: str = Query(..., description="종목코드 또는 티커 (예: 005930, RXRX, AAPL)"),
    timeframe: str = Query("D", description="주기: 'D'(일봉) 또는 'W'(주봉)"),
    days: int = Query(365, description="조회 기간 (일수 단위)")
):
    try:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = fdr.DataReader(symbol, start=start_date)

        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"'{symbol}' 종목 데이터를 찾을 수 없습니다.")

        # 주봉(Weekly) 변환 처리
        if timeframe.upper() == 'W':
            col_map = {col.lower(): col for col in df.columns}
            resample_rule = {}
            if 'open' in col_map: resample_rule[col_map['open']] = 'first'
            if 'high' in col_map: resample_rule[col_map['high']] = 'max'
            if 'low' in col_map: resample_rule[col_map['low']] = 'min'
            if 'close' in col_map: resample_rule[col_map['close']] = 'last'
            if 'adj close' in col_map: resample_rule[col_map['adj close']] = 'last'
            if 'volume' in col_map: resample_rule[col_map['volume']] = 'sum'
            
            df = df.resample('W-MON').agg(resample_rule).dropna()

        # 날짜 인덱스를 컬럼으로 변환
        df = df.reset_index()
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col]).dt.strftime('%Y-%m-%d')

        # 🔥 [중요] NaN(결측치) 처리: NaN을 0으로 채우기
        df = df.fillna(0)

        # JSON 변환 시 NaN 및 numpy 타입 안전 변환
        records = json.loads(df.to_json(orient="records", date_format="iso"))

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "count": len(records),
            "data": records
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 처리 중 오류 발생: {str(e)}")


# 2. 이동평균선(MA) 및 간단 분석 API
@app.get("/api/v1/stock/analysis")
def analyze_stock(
    symbol: str = Query(..., description="종목코드 또는 티커"),
    is_usd: bool = Query(False, description="미국 주식 여부")
):
    try:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        df = fdr.DataReader(symbol, start=start_date)

        if df is None or df.empty or len(df) < 20:
            raise HTTPException(status_code=400, detail="분석하기에 충분한 데이터가 없습니다.")

        df = df.fillna(0)
        close_col = [c for c in df.columns if c.lower() in ['close', 'adj close', 'adj_close']][0]
        
        df['MA5'] = df[close_col].rolling(window=5).mean()
        df['MA20'] = df[close_col].rolling(window=20).mean()

        latest = df.iloc[-1]
        current_price = float(latest[close_col])
        ma5 = float(latest['MA5']) if not np.isnan(latest['MA5']) else current_price
        ma20 = float(latest['MA20']) if not np.isnan(latest['MA20']) else current_price

        if current_price > ma5 > ma20:
            trend = "정배열 상승 추세 (강한 매수 구간)"
            score = 85
        elif current_price < ma5 < ma20:
            trend = "역배열 하락 추세 (관망/손절 구간)"
            score = 35
        else:
            trend = "횡보/조정 구간"
            score = 50

        currency = "$" if is_usd else "원"
        fmt = "{:,.2f}" if is_usd else "{:,.0f}"

        return {
            "symbol": symbol.upper(),
            "current_price": current_price,
            "currency": currency,
            "analysis": {
                "trend": trend,
                "score": score,
                "ma5": round(ma5, 2),
                "ma20": round(ma20, 2)
            },
            "targets": {
                "buy_1st": fmt.format(current_price * 0.98) + currency,
                "buy_2nd": fmt.format(current_price * 0.95) + currency,
                "sell_target": fmt.format(current_price * 1.05) + currency,
                "stop_loss": fmt.format(current_price * 0.93) + currency,
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))