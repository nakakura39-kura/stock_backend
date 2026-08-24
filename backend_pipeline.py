import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, Any, List, Tuple
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity


class MultiTimeframePatternEngine:
    """1일~1주일 트레이딩용 멀티타임프레임 차트 분석 엔진.

    - 월봉: 장기 구조
    - 일봉: 중기 구조 + 과거 유사패턴
    - 60분/15분: 단기 구조
    - 종가/캔들/거래량/ATR/가격위치 반영
    - Top-K 과거 유사사례의 미래 D+1~D+5 경로를 K-Means로 3개 시나리오화
    """

    def __init__(self, forecast_horizon: int = 5, top_k: int = 50):
        self.forecast_horizon = forecast_horizon
        self.top_k = top_k
        self.windows = [5, 10, 20, 60]
        self.window_weights = {5: 0.30, 10: 0.25, 20: 0.25, 60: 0.20}

    # ---------- data ----------
    def fetch_daily(self, code: str, is_us: bool, period: str = "5y") -> pd.DataFrame:
        symbols = [code.upper().strip()]
        if not is_us and code.isdigit():
            symbols = [f"{code}.KS", f"{code}.KQ"]
        for symbol in symbols:
            try:
                df = yf.Ticker(symbol).history(period=period, auto_adjust=False)
                if not df.empty:
                    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                    if len(df) >= 120:
                        return df
            except Exception as e:
                print(f"Daily fetch error {symbol}: {e}")
        return pd.DataFrame()

    def fetch_monthly(self, code: str, is_us: bool, period: str = "10y") -> pd.DataFrame:
        symbols = [code.upper().strip()]
        if not is_us and code.isdigit():
            symbols = [f"{code}.KS", f"{code}.KQ"]
        for symbol in symbols:
            try:
                df = yf.Ticker(symbol).history(period=period, interval="1mo", auto_adjust=False)
                if not df.empty:
                    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            except Exception as e:
                print(f"Monthly fetch error {symbol}: {e}")
        return pd.DataFrame()

    def fetch_intraday(self, code: str, is_us: bool, interval: str = "60m") -> pd.DataFrame:
        # Yahoo 제한을 고려해 60m/15m은 최근 구간만 조회한다.
        period = "60d" if interval == "60m" else "30d"
        symbol = code.upper().strip()
        if not is_us and code.isdigit():
            # KOSPI 우선, 실패하면 KOSDAQ
            candidates = [f"{code}.KS", f"{code}.KQ"]
        else:
            candidates = [symbol]
        for ticker_symbol in candidates:
            try:
                df = yf.Ticker(ticker_symbol).history(period=period, interval=interval, auto_adjust=False)
                if not df.empty:
                    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            except Exception as e:
                print(f"Intraday fetch error {ticker_symbol} {interval}: {e}")
        return pd.DataFrame()

    # ---------- features ----------
    @staticmethod
    def extract_features(df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        close, high, low, op, vol = data["Close"], data["High"], data["Low"], data["Open"], data["Volume"]
        for n in (5, 20, 60, 120):
            data[f"ma{n}"] = close.rolling(n).mean()
            data[f"ma{n}_ratio"] = close / data[f"ma{n"]} - 1.0
        rng = (high - low).replace(0, np.nan)
        data["body_ratio"] = (close - op) / rng
        data["upper_shadow_ratio"] = (high - np.maximum(op, close)) / rng
        data["lower_shadow_ratio"] = (np.minimum(op, close) - low) / rng
        data["close_location"] = (close - low) / rng
        data["gap_ratio"] = op / close.shift(1) - 1.0
        data["vol_ratio"] = vol / vol.rolling(20).mean() - 1.0
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        data["atr_ratio"] = tr.rolling(14).mean() / close
        data["close_pct"] = close.pct_change()
        data["ret5"] = close.pct_change(5)
        data["ret20"] = close.pct_change(20)
        data["position20"] = (close - close.rolling(20).min()) / (close.rolling(20).max() - close.rolling(20).min()).replace(0, np.nan)
        data["position60"] = (close - close.rolling(60).min()) / (close.rolling(60).max() - close.rolling(60).min()).replace(0, np.nan)
        return data.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    @staticmethod
    def _cos(a: np.ndarray, b: np.ndarray) -> float:
        if len(a) != len(b):
            return 0.0
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    @staticmethod
    def _corr(a: np.ndarray, b: np.ndarray) -> float:
        if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    def calculate_similarity(self, current: pd.DataFrame, past: pd.DataFrame) -> float:
        if len(current) != len(past) or len(current) < 2:
            return 0.0
        # 가격/캔들/거래량/변동성/가격위치/이평 구조
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
        if n < max_w + self.forecast_horizon + 60:
            return np.empty((0, self.forecast_horizon)), []
        futures, scores = [], []
        for end in range(max_w, n - self.forecast_horizon):
            score = 0.0
            for w in self.windows:
                current = feat.iloc[-w:]
                past = feat.iloc[end - w:end]
                score += self.calculate_similarity(current, past) * self.window_weights[w]
            base = prices[end - 1]
            future = prices[end:end + self.forecast_horizon] / base - 1.0
            futures.append(future)
            scores.append(score)
        scores_np = np.asarray(scores)
        futures_np = np.asarray(futures)
        idx = np.argsort(scores_np)[::-1][: min(self.top_k, len(scores_np))]
        return futures_np[idx], scores_np[idx].tolist()

    # ---------- timeframe analysis ----------
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
        if float(last.close_location) >= 0.65: score += 8
        if float(last.vol_ratio) >= 0.20: score += 5
        if float(last.ret20) > 0: score += 7
        score = float(np.clip(score, 0, 100))
        if score >= 65: trend = "상승"
        elif score <= 35: trend = "하락"
        else: trend = "중립"
        return {
            "timeframe": label,
            "available": True,
            "close": close,
            "trend": trend,
            "trendScore": round(score, 1),
            "ma5": round(ma5, 4), "ma20": round(ma20, 4), "ma60": round(ma60, 4),
            "closeVsMA20": round(float(last.ma20_ratio) * 100, 2),
            "closeVsMA60": round(float(last.ma60_ratio) * 100, 2),
            "closeLocation": round(float(last.close_location) * 100, 1),
            "volumeRatio": round((float(last.vol_ratio) + 1) * 100, 1),
            "atrRatio": round(float(last.atr_ratio) * 100, 2),
        }

    def close_structure(self, daily: pd.DataFrame) -> Dict[str, Any]:
        f = self.extract_features(daily)
        x = f.iloc[-1]
        return {
            "score": round(float(np.clip(50 + x.close_location * 25 + x.body_ratio * 15 + min(max(x.vol_ratio, -1), 1) * 10, 0, 100)), 1),
            "closeLocation": round(float(x.close_location) * 100, 1),
            "bodyRatio": round(float(x.body_ratio), 3),
            "upperShadowRatio": round(float(x.upper_shadow_ratio), 3),
            "lowerShadowRatio": round(float(x.lower_shadow_ratio), 3),
            "gapRatio": round(float(x.gap_ratio) * 100, 2),
        }

    # ---------- scenario ----------
    def scenarios(self, future_matrix: np.ndarray, similarity_scores: List[float]) -> Dict[str, Any]:
        if len(future_matrix) < 3:
            return {"matchedCount": len(future_matrix), "confidence": 0.0, "scenarios": [], "error": "유사 패턴 부족"}
        k = min(3, len(future_matrix))
        model = KMeans(n_clusters=k, random_state=42, n_init=20)
        labels = model.fit_predict(future_matrix)
        centers = model.cluster_centers_
        scores = np.asarray(similarity_scores, dtype=float)
        # 각 사례의 유사도에 따른 가중 확률
        weights = np.clip(scores, 0.0, 1.0) + 1e-6
        weighted_counts = np.array([weights[labels == i].sum() for i in range(k)])
        probs = weighted_counts / weighted_counts.sum() * 100
        # 최종 수익률로 상승/중립/하락 정렬
        order = np.argsort(centers[:, -1])[::-1]
        scenarios = []
        names = ["상승 지속", "상승 후 조정", "하락 전환"]
        for rank, ci in enumerate(order):
            path = [0.0] + centers[ci].tolist()
            final = float(path[-1])
            # 실제 경로 특성으로 이름 보정
            drawdown = float(np.min(centers[ci]))
            if final < 0:
                name = "하락 전환"
            elif final > 0 and drawdown < -0.02:
                name = "상승 후 조정"
            else:
                name = "상승 지속"
            scenarios.append({
                "rank": rank + 1,
                "name": name if rank < 3 else names[rank],
                "probability": round(float(probs[ci]), 1),
                "finalReturn": round(final * 100, 2),
                "path": [round(float(x) * 100, 3) for x in path],
            })
        confidence = float(np.clip(np.max(probs) * (0.65 + 0.35 * np.mean(scores)), 0, 100))
        return {"matchedCount": len(future_matrix), "confidence": round(confidence, 1), "scenarios": scenarios}

    def analyze(self, daily: pd.DataFrame, monthly: pd.DataFrame, h60: pd.DataFrame, m15: pd.DataFrame) -> Dict[str, Any]:
        matrix, sims = self.search_patterns(daily)
        scenario = self.scenarios(matrix, sims)
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
            "scenario": scenario,
            "similarity": {
                "topK": len(sims),
                "average": round(float(np.mean(sims)) * 100, 1) if sims else 0.0,
                "scores": [round(float(s) * 100, 2) for s in sims[:10]],
            },
        }
