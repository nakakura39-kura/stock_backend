# C:\samsungAI\feature_extractor.py

import pandas as pd
import numpy as np

def get_clv(df: pd.DataFrame) -> pd.Series:
    """Close Location Value (종가 위치 가치: 0.0 ~ 1.0)"""
    rng = df['high'] - df['low']
    val = np.where(rng == 0, 0.5, (df['close'] - df['low']) / rng)
    return pd.Series(val, index=df.index)

def analyze_breakout(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """장중 돌파 vs 종가 돌파 판별"""
    prev_max = df['high'].shift(1).rolling(window=window).max()
    res = pd.DataFrame(index=df.index)
    res['intraday_breakout'] = df['high'] > prev_max
    res['closing_breakout'] = df['close'] > prev_max
    res['fake_breakout'] = res['intraday_breakout'] & (~res['closing_breakout'])
    return res

def get_volume_composite(df: pd.DataFrame) -> pd.Series:
    """거래량 x 가격방향 x CLV 복합 수급 지표"""
    clv = get_clv(df)
    vol_ratio = df['volume'] / df['volume'].rolling(20).mean().fillna(1.0)
    direction = np.sign(df['close'] - df['close'].shift(1)).fillna(0)
    return vol_ratio * direction * (clv + 0.5)

def check_abcd_pullback(df: pd.DataFrame) -> dict:
    """A-B-C-D 눌림목 파동 구조 판별"""
    if df is None or len(df) < 20:
        return {"is_pullback": False, "score": 0}
    
    recent = df.iloc[-20:]
    b_idx = recent['high'].idxmax()
    
    if b_idx != recent.index[-1] and b_idx != recent.index[0]:
        c_df = recent.loc[b_idx:]
        c_low = c_df['low'].min()
        a_low = recent['low'].iloc[0]
        
        if c_low > a_low and c_df['volume'].mean() < recent['volume'].mean():
            return {"is_pullback": True, "score": 85, "c_low": float(c_low)}
            
    return {"is_pullback": False, "score": 0}