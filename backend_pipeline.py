import numpy as np
import pandas as pd
import yfinance as yf
import requests
import json
from typing import Dict, Any, List, Tuple
from sklearn.cluster import KMeans

class MultiTimeframePatternEngine:
    def __init__(self, forecast_horizon: int = 5, top_k: int = 50):
        self.forecast_horizon = forecast_horizon
        self.top_k = top_k
        self.windows = [5, 10, 20, 60]
        self.window_weights = {5: 0.30, 10: 0.25, 20: 0.25, 60: 0.20}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://finance.naver.com/"
        }

    # Data Clean Helper
    @staticmethod
    def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        target_cols = ["Open", "High", "Low", "Close", "Volume"]
        for col in target_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        return df[target_cols].dropna()

    # 네이버 차트 API 우회 크롤러 (한국 주식 전용)
    def _fetch_naver_chart(self, code: str, timeframe: str = "day", count: int = 1250) -> pd.DataFrame:
        clean_code = code.strip().upper().replace(".KS", "").replace(".KQ", "")
        if clean_code.startswith("A") and len(clean_code) == 7 and clean_code[1:].isdigit():
            clean_code = clean_code[1:]

        url = f"https://fchart.stock.naver.com/sise.nhn?symbol={clean_code}&timeframe={timeframe}&count={count}&requestType=0"
        
        try:
            res = requests.get(url, headers=self.headers, timeout=5)
            if res.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(res.text)
                items = root.findall(".//item")
                
                records = []
                for item in items:
                    data = item.get("data", "").split("|")
                    if len(data) >= 6:
                        records.append({
                            "Date": data[0],
                            "Open": float(data[1]),
                            "High": float(data[2]),
                            "Low": float(data[3]),
                            "Close": float(data[4]),
                            "Volume": float(data[5]),
                        })
                
                if records:
                    df = pd.DataFrame(records)
                    df.set_index("Date", inplace=True)
                    return self._clean_df(df)
        except Exception as e:
            print(f"[Naver Fetch Error] Ticker {clean_code} ({timeframe}): {e}")
        
        return pd.DataFrame()

    # ---------- Data Fetching ----------
    def fetch_daily(self, code: str, is_us: bool, period: str = "5y") -> pd.DataFrame:
        symbol = code.upper().strip()
        
        # 한국 주식인 경우 네이버 파이낸스 차트 API 우선 수집 (yfinance IP 차단회피)
        if not is_us:
            df_naver = self._fetch_naver_chart(symbol, timeframe="day", count=1250)
            if not df_naver.empty and len(df_naver) >= 60:
                return df_naver

        # 미국 주식 및 백업용 yfinance
        candidates = [symbol] if is_us else [f"{symbol}.KS", f"{symbol}.KQ"]
        for sym in candidates:
            try:
                df = yf.Ticker(sym).history(period=period, auto_adjust=False)
                cleaned = self._clean_df(df)
                if not cleaned.empty and len(cleaned) >= 60:
                    return cleaned
            except Exception as e:
                print(f"Fetch daily yfinance error for {sym}: {e}")
                
        return pd.DataFrame()

    def fetch_monthly(self, code: str, is_us: bool, period: str = "10y") -> pd.DataFrame:
        symbol = code.upper().strip()
        
        if not is_us:
            df_naver = self._fetch_naver_chart(symbol, timeframe="month", count=120)
            if not df_naver.empty:
                return df_naver

        candidates = [symbol] if is_us else [f"{symbol}.KS", f"{symbol}.KQ"]
        for sym in candidates:
            try:
                df = yf.Ticker(sym).history(period=period, interval="1mo", auto_adjust=False)
                cleaned = self._clean_df(df)
                if not cleaned.empty:
                    return cleaned
            except Exception as e:
                print(f"Fetch monthly error for {sym}: {e}")
        return pd.DataFrame()

    def fetch_intraday(self, code: str, is_us: bool, interval: str = "60m") -> pd.DataFrame:
        period = "60d" if interval == "60m" else "30d"
        symbol = code.upper().strip()
        
        # 한국 주식 분봉 처리
        if not is_us:
            tf = "60" if interval == "60m" else "15"
            df_naver = self._fetch_naver_chart(symbol, timeframe=tf, count=300)
            if not df_naver.empty:
                return df_naver

        candidates = [symbol] if is_us else [f"{symbol}.KS", f"{symbol}.KQ"]
        for sym in candidates:
            try:
                df = yf.Ticker(sym).history(period=period, interval=interval, auto_adjust=False)
                cleaned = self._clean_df(df)
                if not cleaned.empty:
                    return cleaned
            except Exception as e:
                print(f"Fetch intraday error for {sym} ({interval}): {e}")
        return pd.DataFrame()

    # ---------- Feature Extraction ----------
    @staticmethod
    def extract_features(df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        close, high, low, op, vol = data["Close"], data["High"], data["Low"], data["Open"], data["Volume"]
        
        for n in (5, 20, 60, 120):
            data[f"ma{n}"] = close.rolling(n).mean()
            data[f"ma{n}_ratio"] = close / data[f"ma{n}"] - 1.0

        rng = (high - low).replace(0, np.nan).fillna(0.0001)
        
        data["body_ratio"] = (close - op) / rng
        data["upper_shadow_ratio"] = (high - np.maximum(op, close)) / rng
        data["lower_shadow_ratio"] = (np.minimum(op, close) - low) / rng
        data["close_location"] = (close - low) / rng
        data["gap_ratio"] = op / close.shift(1) - 1.0
        
        vol_ma20 = vol.rolling(20).mean().replace(0, np.nan).fillna(1.0)
        data["vol_ratio"] = vol / vol_ma20 - 1.0

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        data["atr_ratio"] = tr.rolling(14).mean() / close

        data["close_pct"] = close.pct_change()
        
        p20_diff = (close.rolling(20).max() - close.rolling(20).min()).replace(0, np.nan).fillna(1.0)
        p60_diff = (close.rolling(60).max() - close.rolling(60).min()).replace(0, np.nan).fillna(1.0)
        
        data["position20"] = (close - close.rolling(20).min()) / p20_diff
        data["position60"] = (close - close.rolling(60).min()) / p60_diff
        
        return data.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    # ---------- Similarity Calculations ----------
    @staticmethod
    def _cos(a: np.ndarray, b: np.ndarray) -> float:
        if len(a) != len(b): return 0.0
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        return float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0

    @staticmethod
    def _corr(a: np.ndarray, b: np.ndarray) -> float:
        if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0: return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    def calculate_similarity(self, current: pd.DataFrame, past: pd.DataFrame) -> float:
        if len(current) != len(past) or len(current) < 2: return 0.0
        
        price = 0.5 * self._cos(current.close_pct.values, past.close_pct.values) + 0.5 * ((self._corr(current.close_pct.values, past.close_pct.values) + 1) / 2)
        
        ma_cur = np.column_stack([current.ma5_ratio, current.ma20_ratio, current.ma60_ratio, current.ma120_ratio]).flatten()
        ma_past = np.column_stack([past.ma5_ratio, past.ma20_ratio, past.ma60_ratio, past.ma120_ratio]).flatten()
        ma = 0.5 * self._cos(ma_cur, ma_past) + 0.5 * ((self._corr(ma_cur, ma_past) + 1) / 2)

        candle_cur = np.column_stack([current.body_ratio, current.upper_shadow_ratio, current.lower_shadow_ratio, current.close_location, current.gap_ratio]).flatten()
        candle_past = np.column_stack([past.body_ratio, past.upper_shadow_ratio, past.lower_shadow_ratio, past.close_location, past.gap_ratio]).flatten()
        candle = 0.5 * self._cos(candle_cur, candle_past) + 0.5 * ((self._corr(candle_cur, candle_past) + 1) / 2)

        volume = 0.5 * self._cos(current.vol_ratio.values, past.vol_ratio.values) + 0.5 * ((self._corr(current.vol_ratio.values, past.vol_ratio.values) + 1) / 2)
        volatility = 0.5 * self._cos(current.atr_ratio.values, past.atr_ratio.values) + 0.5 * ((self._corr(current.atr_ratio.values, past.atr_ratio.values) + 1) / 2)
        position = 0.5 * self._cos(current.position20.values, past.position20.values) + 0.5 * ((self._corr(current.position20.values, past.position20.values) + 1) / 2)

        score = 0.28 * price + 0.22 * ma + 0.18 * candle + 0.12 * volume + 0.10 * volatility + 0.10 * position
        return float(np.clip(score, 0.0, 1.0))

    def search_patterns(self, df: pd.DataFrame) -> Tuple[np.ndarray, List[float]]:
        feat = self.extract_features(df)
        prices = df["Close"].values.astype(float)
        n = len(df)
        max_w = max(self.windows)
        if n < max_w + self.forecast_horizon + 10:
            return np.empty((0, self.forecast_horizon)), []

        futures, scores = [], []
        for end in range(max_w, n - self.forecast_horizon):
            score = sum(self.calculate_similarity(feat.iloc[-w:], feat.iloc[end - w:end]) * self.window_weights[w] for w in self.windows)
            base = prices[end - 1]
            future = prices[end:end + self.forecast_horizon] / base - 1.0
            futures.append(future)
            scores.append(score)

        scores_np = np.asarray(scores)
        futures_np = np.asarray(futures)
        if len(scores_np) == 0:
            return np.empty((0, self.forecast_horizon)), []

        idx = np.argsort(scores_np)[::-1][: min(self.top_k, len(scores_np))]
        return futures_np[idx], scores_np[idx].tolist()

    # ---------- 타임프레임별 분석 ----------
    @staticmethod
    def timeframe_summary(df: pd.DataFrame, label: str) -> Dict[str, Any]:
        if df.empty or len(df) < 2:
            return {"timeframe": label, "available": False}
        f = MultiTimeframePatternEngine.extract_features(df)
        last = f.iloc[-1]
        close = float(last.Close)
        ma5, ma20, ma60 = float(last.ma5), float(last.ma20), float(last.ma60)

        score = 50.0
        if close > ma20: score += 15
        if ma20 > ma60: score += 15
        if float(last.close_location) >= 0.65: score += 10
        if float(last.vol_ratio) >= 0.20: score += 10

        score = float(np.clip(score, 0, 100))
        trend = "상승" if score >= 65 else ("하락" if score <= 35 else "중립")

        return {
            "timeframe": label,
            "available": True,
            "close": close,
            "trend": trend,
            "trendScore": round(score, 1),
            "ma5": round(ma5, 2), "ma20": round(ma20, 2), "ma60": round(ma60, 2),
            "closeVsMA20": round(float(last.ma20_ratio) * 100, 2),
            "closeVsMA60": round(float(last.ma60_ratio) * 100, 2),
            "closeLocation": round(float(last.close_location) * 100, 1),
            "volumeRatio": round((float(last.vol_ratio) + 1) * 100, 1),
            "atrRatio": round(float(last.atr_ratio) * 100, 2),
        }

    # ---------- 종가 구조 분석 ----------
    def close_structure(self, daily: pd.DataFrame) -> Dict[str, Any]:
        if daily.empty: return {}
        f = self.extract_features(daily)
        x = f.iloc[-1]
        
        strength_score = np.clip(
            50 + (x.close_location - 0.5) * 40 + x.body_ratio * 20 + min(max(x.vol_ratio, -1), 1) * 10,
            0, 100
        )
        return {
            "score": round(float(strength_score), 1),
            "closeLocation": round(float(x.close_location) * 100, 1),
            "bodyRatio": round(float(x.body_ratio), 3),
            "upperShadowRatio": round(float(x.upper_shadow_ratio), 3),
            "lowerShadowRatio": round(float(x.lower_shadow_ratio), 3),
            "gapRatio": round(float(x.gap_ratio) * 100, 2),
            "position20": round(float(x.position20) * 100, 1),
            "position60": round(float(x.position60) * 100, 1),
        }

    # ---------- 동적 시나리오 판별 ----------
    def scenarios(self, future_matrix: np.ndarray, similarity_scores: List[float]) -> Dict[str, Any]:
        n_samples = len(future_matrix)
        if n_samples < 3:
            return {"matchedCount": n_samples, "confidence": 0.0, "scenarios": [], "error": "유사 패턴 부족"}

        k = min(3, n_samples)
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(future_matrix)
        centers = model.cluster_centers_

        scores = np.asarray(similarity_scores, dtype=float)
        weights = np.clip(scores, 0.0, 1.0) + 1e-6
        weighted_counts = np.array([weights[labels == i].sum() for i in range(k)])
        probs = (weighted_counts / weighted_counts.sum()) * 100

        scenarios = []
        for i in range(k):
            path = [0.0] + centers[i].tolist()
            final_return = float(path[-1])
            max_drawdown = float(np.min(centers[i]))

            if final_return < -0.01:
                name = "하락 전환"
            elif final_return > 0.01 and max_drawdown < -0.015:
                name = "상승 후 조정"
            elif final_return > 0.01:
                name = "상승 지속"
            else:
                name = "박스권 횡보"

            scenarios.append({
                "name": name,
                "probability": round(float(probs[i]), 1),
                "finalReturn": round(final_return * 100, 2),
                "path": [round(float(x) * 100, 3) for x in path],
                "sampleCount": int(np.sum(labels == i))
            })

        scenarios = sorted(scenarios, key=lambda x: x["probability"], reverse=True)
        for idx, sc in enumerate(scenarios):
            sc["rank"] = idx + 1

        sample_score = min(1.0, n_samples / 50.0) * 30
        avg_sim = np.mean(scores) * 40
        confidence = round(sample_score + avg_sim + (scenarios[0]["probability"] * 0.3), 1)

        return {
            "matchedCount": n_samples,
            "confidence": min(99.0, max(10.0, confidence)),
            "scenarios": scenarios
        }

    def analyze(self, daily: pd.DataFrame, monthly: pd.DataFrame, h60: pd.DataFrame, m15: pd.DataFrame) -> Dict[str, Any]:
        matrix, sims = self.search_patterns(daily)
        scenario_res = self.scenarios(matrix, sims)
        current = float(daily.Close.iloc[-1]) if not daily.empty else 0.0

        return {
            "currentPrice": current,
            "timeframes": {
                "monthly": self.timeframe_summary(monthly, "월봉"),
                "daily": self.timeframe_summary(daily, "일봉"),
                "hour60": self.timeframe_summary(h60, "60분봉"),
                "minute15": self.timeframe_summary(m15, "15분봉"),
            },
            "closeStructure": self.close_structure(daily),
            "scenario": scenario_res,
            "similarity": {
                "topK": len(sims),
                "average": round(float(np.mean(sims)) * 100, 1) if sims else 0.0,
            },
        }