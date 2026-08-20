# C:\samsungAI\indicators.py

import pandas as pd
import numpy as np

def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """이동평균선, RSI, 볼린저밴드, MACD 지표 생성"""
    if df is None or df.empty or len(df) < 5:
        return df
        
    df = df.copy()
    
    # 1. 이동평균선 (SMA)
    for window in [5, 10, 20, 60, 120]:
        if len(df) >= window:
            df[f'sma_{window}'] = df['close'].rolling(window=window).mean()
        else:
            df[f'sma_{window}'] = df['close']
        
    # 2. RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=min(14, len(df))).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=min(14, len(df))).mean()
    rs = gain / (loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 3. 볼린저 밴드 (20일)
    ma20 = df['sma_20'] if 'sma_20' in df.columns else df['close']
    std20 = df['close'].rolling(window=min(20, len(df))).std().fillna(0)
    df['bb_upper'] = ma20 + (std20 * 2)
    df['bb_lower'] = ma20 - (std20 * 2)
    
    # 4. MACD (12, 26, 9)
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    return df