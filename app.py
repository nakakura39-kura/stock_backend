import os
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import torch
import torch.nn as nn
import plotly.graph_objects as go

# 1. 페이지 및 모바일 UI 기본 설정
st.set_page_config(
    page_title="AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "weights")
MODEL_PATH = os.path.join(WEIGHTS_DIR, "stock_model.pt")

# 2. LSTM 모델 정의
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
        out = self.fc(out[:, -1, :])
        return out

@st.cache_data(ttl=3600)
def load_stock_data(ticker, start="2024-01-01"):
    df = yf.download(ticker, start=start)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={'Close': 'close', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Volume': 'volume'})
    return df.dropna()

def get_ai_prediction(df, seq_len=20):
    if not os.path.exists(MODEL_PATH):
        return None, 0.5

    df_feat = df.copy()
    df_feat['ret'] = df_feat['close'].pct_change()
    df_feat['sma5'] = df_feat['close'].rolling(5).mean() / df_feat['close'] - 1
    df_feat['sma20'] = df_feat['close'].rolling(20).mean() / df_feat['close'] - 1
    df_feat = df_feat.fillna(0)

    features = df_feat[['close', 'ret', 'sma5', 'sma20']].values
    mean, std = features.mean(axis=0), features.std(axis=0) + 1e-8
    features = (features - mean) / std

    xs = []
    for i in range(len(features)):
        if i < seq_len:
            pad = np.tile(features[0], (seq_len - i - 1, 1))
            seq = np.vstack([pad, features[:i+1]])
        else:
            seq = features[i - seq_len + 1:i + 1]
        xs.append(seq)

    x_tensor = torch.tensor(np.array(xs), dtype=torch.float32)
    model = LSTMPredictor(input_size=4, hidden_size=64, num_layers=2)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=torch.device('cpu')))
    model.eval()

    with torch.no_grad():
        probs = model(x_tensor).numpy().flatten()

    return (probs > 0.5).astype(int), probs[-1]

# 3. 사이드바 메인 메뉴
st.sidebar.title("📱 AI 트레이딩 탭")
menu = st.sidebar.radio("메뉴 선택", ["🔍 종목 분석 & 분할 매매", "🤖 AI 예측 그래프"])

# 종목 선택
ticker_input = st.sidebar.text_input("종목코드 입력 (예: 005930.KS, NVDA, TSLA, AAPL)", "005930.KS")
df = load_stock_data(ticker_input)
signals, latest_prob = get_ai_prediction(df)

current_price = float(df['close'].iloc[-1])

# --- [메뉴 1] 종목 분석 & 분할 매매 ---
if menu == "🔍 종목 분석 & 분할 매매":
    st.header(f"📊 {ticker_input} 보유 현황 및 분할 매매 가이드")
    st.caption(f"현재가: **{current_price:,.0f}** | AI 상상 확률: **{latest_prob*100:.1f}%**")

    col1, col2 = st.columns(2)
    with col1:
        cash = st.number_input("보유 예수금 (KRW / USD)", value=5000000, step=100000)
        hold_qty = st.number_input("보유 주식 수량", value=50, step=1)
    with col2:
        avg_price = st.number_input("평균 단가 (평단가)", value=float(current_price * 1.05), step=100.0)

    # 손익 계산
    total_eval = hold_qty * current_price
    total_cost = hold_qty * avg_price
    pnl = total_eval - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("총 평가 금액", f"{total_eval:,.0f}")
    m2.metric("평가 손익", f"{pnl:,.0f}", delta=f"{pnl_pct:.2f}%")
    m3.metric("AI 추천 스탠스", "매수 / 홀딩" if latest_prob > 0.5 else "비중 축소 / 매도")

    st.subheader("💡 AI 추천 분할 매수 / 매도 가격 가이드")
    
    # ATR 기반 변동성 가이드 라인 계산
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
    
    b1, b2, b3 = current_price - (atr * 0.5), current_price - (atr * 1.0), current_price - (atr * 1.5)
    s1, s2, s3 = current_price + (atr * 0.5), current_price + (atr * 1.0), current_price + (atr * 1.5)

    tab_buy, tab_sell = st.tabs(["📉 분할 매수 라인", "📈 분할 매도 라인"])
    
    with tab_buy:
        buy_df = pd.DataFrame({
            "차수": ["1차 매수 (-0.5 ATR)", "2차 매수 (-1.0 ATR)", "3차 매수 (-1.5 ATR)"],
            "권장 단가": [f"{b1:,.1f}", f"{b2:,.1f}", f"{b3:,.1f}"],
            "권장 비중": ["예수금의 20%", "예수금의 30%", "예수금의 50%"],
            "투입 금액": [f"{cash*0.2:,.0f}", f"{cash*0.3:,.0f}", f"{cash*0.5:,.0f}"]
        })
        st.table(buy_df)

    with tab_sell:
        sell_df = pd.DataFrame({
            "차수": ["1차 익절 (+0.5 ATR)", "2차 익절 (+1.0 ATR)", "3차 익절 (+1.5 ATR)"],
            "목표 단가": [f"{s1:,.1f}", f"{s2:,.1f}", f"{s3:,.1f}"],
            "매도 비중": ["보유량의 30%", "보유량의 30%", "잔여 전량"],
            "매도 수량": [f"{int(hold_qty*0.3)} 주", f"{int(hold_qty*0.3)} 주", f"{hold_qty - int(hold_qty*0.3)*2} 주"]
        })
        st.table(sell_df)

# --- [메뉴 2] AI 예측 그래프 ---
elif menu == "🤖 AI 예측 그래프":
    st.header(f"📈 {ticker_input} LSTM 주가 예측 & 백테스트 시뮬레이션")
    
    df['market_ret'] = df['close'].pct_change()
    df['strategy_ret'] = df['market_ret'] * pd.Series(signals, index=df.index).shift(1)
    df['cum_strategy'] = (1 + df['strategy_ret'].fillna(0)).cumprod() * 10000000

    # Plotly 대화형 인터랙티브 차트
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['close'], mode='lines', name='실제 주가 (Close)', line=dict(color='#888888', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df['cum_strategy'] / df['cum_strategy'].iloc[0] * df['close'].iloc[0], 
                             mode='lines', name='AI 전략 수익 곡선', line=dict(color='#00CC96', width=2)))

    fig.update_layout(title="주가 추이 vs AI 모델 포트폴리오 성과", xaxis_title="날짜", yaxis_title="주가", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 AI 예측 시그널 백테스트 지표")
    total_ret = ((df['cum_strategy'].iloc[-1] / 10000000) - 1) * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric("백테스트 수익률", f"{total_ret:.2f}%")
    col2.metric("최근 AI 상승 확률", f"{latest_prob*100:.1f}%")
    col3.metric("최종 시그널", "BUY" if latest_prob > 0.5 else "HOLD / SELL")