from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
import yfinance as yf
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import joblib
import sys
import os
from datetime import datetime, timedelta

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 동일 폴더 내 features_V11_2.py 임포트
try:
    import features_V11_2 as ft
except ImportError:
    ft = None
    print("[WARN] features_V11_2.py 파일을 찾을 수 없습니다.")

app = FastAPI(title="Stock AI Scalping Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= ================= =================
# 1. AI 모델 로드 (v14 Entry & Exit Soft Voting Dual System)
# ================= ================= =================
ENTRY_MODEL_PATH = "scalping_ai_v14_entry_sw.pkl"
EXIT_MODEL_PATH = "scalping_ai_v14_exit_sw.pkl"

entry_model = None
exit_model = None

if os.path.exists(ENTRY_MODEL_PATH):
    try:
        entry_model = joblib.load(ENTRY_MODEL_PATH)
        print(f"[OK] AI Entry model ({ENTRY_MODEL_PATH}) loaded successfully.")
    except Exception as e:
        print(f"[ERROR] Entry model load error: {e}")

if os.path.exists(EXIT_MODEL_PATH):
    try:
        exit_model = joblib.load(EXIT_MODEL_PATH)
        print(f"[OK] AI Exit model ({EXIT_MODEL_PATH}) loaded successfully.")
    except Exception as e:
        print(f"[ERROR] Exit model load error: {e}")

import urllib.parse
STOCK_MAP = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "NAVER": "035420",
    "카카오": "035720",
    "현대차": "005380"
}
STOCK_MAP_REV = {v: k for k, v in STOCK_MAP.items()}

def resolve_stock_info(query: str, is_us_hint: bool = None) -> dict:
    """종목명 또는 코드를 분석하여 정확한 (code, name, is_us) 정보를 반환합니다."""
    q = query.strip()
    if not q:
        return {"code": "005930", "name": "삼성전자", "is_us": False}

    # 1. 6자리 숫자인 경우 (한국 주식 코드)
    if q.isdigit() and len(q) == 6:
        name = STOCK_MAP_REV.get(q, q)
        if name == q:
            try:
                eq = urllib.parse.quote(q)
                url = f"https://m.stock.naver.com/front-api/search/autoComplete?query={eq}&target=stock"
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
                if res.status_code == 200:
                    stocks = res.json().get('result', {}).get('stock', [])
                    if stocks:
                        name = stocks[0].get('name', q)
            except Exception:
                pass
        return {"code": q, "name": name, "is_us": False}

    # 2. STOCK_MAP에 정의된 한국 종목명인 경우
    if q in STOCK_MAP:
        return {"code": STOCK_MAP[q], "name": q, "is_us": False}

    # 3. 순수 영문(ASCII 문자) 티커인 경우 (예: RXRX, AAPL, TSLA, NVDA 등)
    # 단, 사용자가 명시적으로 is_us_hint=False를 주지 않은 한 영문 티커는 미국 주식으로 판별
    if q.isascii() and q.isalpha() and len(q) <= 6:
        if is_us_hint is not False:
            ticker = q.upper()
            return {"code": ticker, "name": ticker, "is_us": True}

    # 4. 한글 종목명 또는 그 외 검색어 -> 네이버 모바일 자동완성 API 검색
    try:
        eq = urllib.parse.quote(q)
        url = f"https://m.stock.naver.com/front-api/search/autoComplete?query={eq}&target=stock"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        if res.status_code == 200:
            stocks = res.json().get('result', {}).get('stock', [])
            if stocks:
                first = stocks[0]
                return {
                    "code": str(first.get('code')),
                    "name": str(first.get('name')),
                    "is_us": False
                }
    except Exception as e:
        print(f"네이버 종목 검색 에러 ({q}): {e}")

    # 5. 검색되지 않았으나 순수 영문인 경우 미국 주식 티커로 처리
    if q.isascii():
        ticker = q.upper()
        return {"code": ticker, "name": ticker, "is_us": True}

    # 최종 fallback: 입력값 그대로 한국 종목으로 반환
    return {"code": q, "name": q, "is_us": False}


def safe_float(value, default=0.0) -> float:
    if not value or str(value).strip().lower() in ['null', 'none', '']:
        return default
    try:
        return float(str(value).replace(',', ''))
    except ValueError:
        return default

# ================= ================= =================
# 2. 데이터 수집
# ================= ================= =================

def fetch_naver_minute_chart(code: str, timeframe: str = 'm5', count: int = 150) -> list:
    timeframe_val = "5" if timeframe == 'm5' else "60"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=minute&count={count}&requestType=0&timeframeValue={timeframe_val}"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200 and res.text.strip().startswith("<?xml"):
            root = ET.fromstring(res.text)
            chartdata = root.find('chartdata')
            if chartdata is not None:
                items = chartdata.findall('item')
                result_list = []
                for item in items:
                    parts = item.attrib.get('data', '').split('|')
                    if len(parts) >= 6:
                        raw_time = parts[0]
                        fmt_time = f"{raw_time[:4]}-{raw_time[4:6]}-{raw_time[6:8]} {raw_time[8:10]}:{raw_time[10:12]}:00" if len(raw_time) >= 12 else raw_time
                        close_p = safe_float(parts[4])
                        if close_p > 0:
                            result_list.append({
                                "time": fmt_time,
                                "open": safe_float(parts[1], close_p),
                                "high": safe_float(parts[2], close_p),
                                "low": safe_float(parts[3], close_p),
                                "close": close_p,
                                "volume": safe_float(parts[5])
                            })
                return result_list
    except Exception as e:
        print(f"네이버 수집 에러 ({code}): {e}")
    return []

def fetch_us_minute_chart(code: str, timeframe: str = 'm5', count: int = 150) -> list:
    tf_map = {'m5': '5m', 'm15': '15m', 'm60': '60m'}
    interval = tf_map.get(timeframe, '5m')
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(period="5d", interval=interval)
        if df.empty:
            return []
        result_list = []
        target_df = df.tail(count) if len(df) >= count else df
        for index, row in target_df.iterrows():
            result_list.append({
                "time": index.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(safe_float(row['Open']), 2),
                "high": round(safe_float(row['High']), 2),
                "low": round(safe_float(row['Low']), 2),
                "close": round(safe_float(row['Close']), 2),
                "volume": safe_float(row['Volume'])
            })
        return result_list
    except Exception as e:
        print(f"미국 수집 에러 ({code}): {e}")
        return []

# ================= ================= =================
# 3. AI 추론 및 파동 범주 파이프라인
# ================= ================= =================

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def prepare_candles_for_feature_engine(candles_df: pd.DataFrame, code: str = "005930") -> pd.DataFrame:
    df = candles_df.copy()
    df['code'] = code
    df['event_type'] = 'TRADE'
    df['datetime'] = pd.to_datetime(df['time']) if 'time' in df.columns else pd.date_range(end=pd.Timestamp.now(), periods=len(df), freq='5min')
    df['timestamp'] = df['datetime'].astype('int64') // 10**9
    df['price'] = df['close']
    df['trade_volume'] = df['volume']
    df['change_rate'] = df['close'].pct_change().fillna(0) * 100
    df['execution_strength'] = 100.0
    df['ask_total'] = df['volume'] * 0.5
    df['bid_total'] = df['volume'] * 0.5
    df['ask_total_delta'] = 0.0
    df['bid_total_delta'] = 0.0
    df['net_bid_qty'] = 0.0
    df['bid_ratio'] = 50.0
    df['net_ask_qty'] = 0.0
    df['ask_ratio'] = 50.0
    for i in range(1, 11):
        df[f'ask_price_{i}'] = df['price'] + (i * 10)
        df[f'bid_price_{i}'] = df['price'] - (i * 10)
        df[f'ask_qty_{i}'] = df['volume'] / 10
        df[f'bid_qty_{i}'] = df['volume'] / 10
        df[f'ask_delta_{i}'] = 0.0
        df[f'bid_delta_{i}'] = 0.0
    return df

def predict_single_model(model_raw, feat_df: pd.DataFrame) -> float:
    if model_raw is None or feat_df.empty:
        return 50.0
    try:
        model_obj = model_raw
        model_feature_names = None
        if isinstance(model_raw, dict):
            for key in ['model', 'estimator', 'classifier', 'scalping_model', 'lgb', 'xgb']:
                if key in model_raw:
                    model_obj = model_raw[key]
                    break
            for key in ['features', 'feature_names', 'feature_list', 'columns', 'cols']:
                if key in model_raw:
                    model_feature_names = model_raw[key]
                    break

        feature_cols = model_feature_names or getattr(model_obj, "feature_names_in_", None)
        if feature_cols is not None:
            for col in [c for c in feature_cols if c not in feat_df.columns]:
                feat_df[col] = 0.0
            X = feat_df[feature_cols].tail(1)
        else:
            X = feat_df.tail(1)

        if hasattr(model_obj, "predict_proba"):
            probs = model_obj.predict_proba(X)[0]
            prob = probs[1] if len(probs) > 1 else probs[0]
        elif hasattr(model_obj, "predict"):
            pred = model_obj.predict(X)[0]
            prob = pred if 0 <= pred <= 1 else 0.5
        else:
            prob = 0.5

        return round(float(prob) * 100, 1)
    except Exception as e:
        print(f"추론 중 에러: {e}")
        return 50.0

def predict_ai_duo_signals(candles_df: pd.DataFrame, code: str = "005930") -> dict:
    if ft is None or len(candles_df) < 30:
        return {"entry_prob": 50.0, "exit_prob": 50.0}
    try:
        prep_df = prepare_candles_for_feature_engine(candles_df, code=code)
        feat_df = ft.make_features_for_stock(prep_df)
        if feat_df.empty:
            return {"entry_prob": 50.0, "exit_prob": 50.0}
        return {
            "entry_prob": predict_single_model(entry_model, feat_df.copy()),
            "exit_prob": predict_single_model(exit_model, feat_df.copy())
        }
    except Exception as e:
        print(f"AI Duo 에러: {e}")
        return {"entry_prob": 50.0, "exit_prob": 50.0}

# 2시간 변곡 파동 계산기
def generate_2hr_range_path(current_price: float, entry_prob: float, exit_prob: float, is_us: bool):
    entry_score = entry_prob / 100.0
    exit_score = exit_prob / 100.0
    
    # 2시간 동안 최대 상승/하락 범위 변수 설정
    upper_max = current_price * (1.0 + (entry_score * 0.05) + 0.01)
    lower_min = current_price * (1.0 - (exit_score * 0.04) - 0.01)
    
    range_path = []
    # 15분 간격 8개 구간 (총 120분)
    for i in range(1, 9):
        minutes = i * 15
        ratio = i / 8.0
        
        # 사인 파동을 활용한 2시간 실시간 변곡선 생성
        wave = np.sin(ratio * np.pi) * (entry_score - exit_score) * 0.04
        expected_p = current_price * (1.0 + wave + ((entry_score - 0.5) * 0.03 * ratio))
        upper_p = current_price + ((upper_max - current_price) * np.sqrt(ratio))
        lower_p = current_price - ((current_price - lower_min) * np.sqrt(ratio))

        range_path.append({
            "minute": minutes,
            "expected": round(expected_p, 2 if is_us else 0),
            "upper": round(upper_p, 2 if is_us else 0),
            "lower": round(lower_p, 2 if is_us else 0),
        })
    return range_path, upper_max, lower_min

# ================= ================= =================
# 4. API 엔드포인트
# ================= ================= =================

@app.get("/search")
async def search_stock(q: str = Query(..., description="검색어")):
    info = resolve_stock_info(q)
    return [{"code": info["code"], "name": info["name"], "is_us": info["is_us"]}]

@app.get("/analyze")
async def analyze_stock(
    code: str = Query("RXRX", description="종목 코드 또는 종목명"),
    is_us: bool = Query(None, description="미국 주식 여부 (선택, 미지정 시 자동 판별)"),
    balance: float = Query(5000000, description="예수금"),
    shares: int = Query(2, description="보유 수량"),
    avg_price: float = Query(0.0, description="평단가")
):
    info = resolve_stock_info(code, is_us_hint=is_us)
    target_code = info["code"]
    stock_name = info["name"]
    is_us_stock = info["is_us"]

    candles = fetch_us_minute_chart(target_code, timeframe='m5', count=150) if is_us_stock else fetch_naver_minute_chart(target_code, timeframe='m5', count=150)
    
    # 만약 수집 실패 시 반대 시장으로 자동 전환 시도 (안전장치)
    if not candles:
        if is_us_stock and target_code.isdigit() and len(target_code) == 6:
            candles = fetch_naver_minute_chart(target_code, timeframe='m5', count=150)
            if candles:
                is_us_stock = False
        elif not is_us_stock and target_code.isascii() and target_code.isalpha():
            candles = fetch_us_minute_chart(target_code, timeframe='m5', count=150)
            if candles:
                is_us_stock = True

    if not candles:
        market_str = "미국" if is_us_stock else "국내"
        return {"status": "error", "message": f"{stock_name}({target_code}) {market_str} 차트 데이터를 불러올 수 없습니다."}

    df_candles = pd.DataFrame(candles)
    closes = df_candles['close'].tolist()
    current_price = closes[-1]

    rsi = calculate_rsi(closes, 14)
    ai_res = predict_ai_duo_signals(df_candles, code=target_code)
    entry_prob = ai_res["entry_prob"]
    exit_prob = ai_res["exit_prob"]

    # 2시간 예상 경로 및 변곡 범위 생성
    range_path, upper_max, lower_min = generate_2hr_range_path(current_price, entry_prob, exit_prob, is_us_stock)

    target_entry = round(current_price * 0.99, 2 if is_us_stock else 0)
    target_exit = round(upper_max, 2 if is_us_stock else 0)
    stop_loss = round(lower_min, 2 if is_us_stock else 0)

    fmt = lambda p: f"${p:,.2f}" if is_us_stock else f"{int(p):,}원"

    return {
        "status": "success",
        "code": target_code,
        "name": stock_name,
        "current_price": current_price,
        "is_us": is_us_stock,
        "scalping_analysis": {
            "entry_confidence": entry_prob,
            "exit_risk": exit_prob,
            "entry_signal": entry_prob >= 60.0,
            "target_entry_price": target_entry,
            "target_exit_price": target_exit,
            "stop_loss_price": stop_loss,
            "rsi": rsi,
            "range_path": range_path
        },
        "order_table": [
            {"id": 1, "type": "추천 진입가", "weight": "50%", "target_price": fmt(target_entry)},
            {"id": 2, "type": "목표 청산가", "weight": "50%", "target_price": fmt(target_exit)},
            {"id": 3, "type": "손절 대응가", "weight": "100%", "target_price": fmt(stop_loss)}
        ]
    }