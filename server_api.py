import os
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Stock AI Server")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(CURRENT_DIR, "weights", "stock_model.pt")

# 기존 LSTM 모델 구조 동일 유지
class LSTMPredictor(nn.Module):
    def __init__(self, input_size=4, hidden_size=64, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])

# Flutter 앱에서 넘겨받을 요청 데이터 구조 (예수금, 평단가 등 추가)
class AnalyzeRequest(BaseModel):
    ticker: str
    cash: float
    hold_qty: int
    avg_price: float

@app.post("/api/analyze")
def analyze_stock(req: AnalyzeRequest):
    # 1. 최신 주가 데이터 수집
    df = yf.download(req.ticker, start="2024-01-01")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={'Close': 'close', 'High': 'high', 'Low': 'low'}).dropna()

    current_price = float(df['close'].iloc[-1])
    
    # 2. 보유 주식 손익 평가 계산
    total_eval = req.hold_qty * current_price
    total_cost = req.hold_qty * req.avg_price
    pnl = total_eval - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0

    # 3. 기존 LSTM AI 예측 시그널 계산
    df_feat = df.copy()
    df_feat['ret'] = df_feat['close'].pct_change()
    df_feat['sma5'] = df_feat['close'].rolling(5).mean() / df_feat['close'] - 1
    df_feat['sma20'] = df_feat['close'].rolling(20).mean() / df_feat['close'] - 1
    df_feat = df_feat.fillna(0)

    features = df_feat[['close', 'ret', 'sma5', 'sma20']].values
    features = (features - features.mean(axis=0)) / (features.std(axis=0) + 1e-8)

    seq = features[-20:]
    x_tensor = torch.tensor(np.array([seq]), dtype=torch.float32)

    model = LSTMPredictor()
    if os.path.exists(MODEL_PATH):
        model.load_state_dict(torch.load(MODEL_PATH, map_location='cpu'))
    model.eval()

    with torch.no_grad():
        prob = float(model(x_tensor).numpy()[0][0])

    # 4. ATR 변동성 기반 분할 매수/매도 라인 추가 계산
    atr = float((df['high'] - df['low']).rolling(14).mean().iloc[-1])
    
    buy_levels = [
        {"step": "1차 매수 (-0.5 ATR)", "price": round(current_price - atr * 0.5, 1), "amount": round(req.cash * 0.2)},
        {"step": "2차 매수 (-1.0 ATR)", "price": round(current_price - atr * 1.0, 1), "amount": round(req.cash * 0.3)},
        {"step": "3차 매수 (-1.5 ATR)", "price": round(current_price - atr * 1.5, 1), "amount": round(req.cash * 0.5)},
    ]

    sell_levels = [
        {"step": "1차 익절 (+0.5 ATR)", "price": round(current_price + atr * 0.5, 1), "qty": int(req.hold_qty * 0.3)},
        {"step": "2차 익절 (+1.0 ATR)", "price": round(current_price + atr * 1.0, 1), "qty": int(req.hold_qty * 0.3)},
        {"step": "3차 익절 (+1.5 ATR)", "price": round(current_price + atr * 1.5, 1), "qty": req.hold_qty - int(req.hold_qty * 0.3) * 2},
    ]

    # 5. 차트 데이터 (최근 60일)
    chart_data = df['close'].tail(60).reset_index()
    chart_list = [{"date": str(row['Date'])[:10], "close": float(row['close'])} for _, row in chart_data.iterrows()]

    return {
        "ticker": req.ticker,
        "current_price": current_price,
        "total_eval": total_eval,
        "pnl": round(pnl),
        "pnl_pct": round(pnl_pct, 2),
        "ai_probability": round(prob * 100, 1),
        "stance": "매수 / 홀딩" if prob > 0.5 else "비중 축소 / 매도",
        "buy_levels": buy_levels,
        "sell_levels": sell_levels,
        "chart": chart_list
    }