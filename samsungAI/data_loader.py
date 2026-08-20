# C:\samsungAI\data_loader.py

import FinanceDataReader as fdr
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명을 소문자로 통일하고 해외 주식 MultiIndex 컬럼 및 중복 컬럼 정제"""
    if df is None or df.empty:
        return pd.DataFrame()
        
    df = df.copy()
    
    # 해외 주식 수집 시 MultiIndex 컬럼인 경우 1차원으로 평탄화
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    df.columns = [str(col).lower() for col in df.columns]
    
    rename_map = {
        'open': 'open', 'high': 'high', 'low': 'low', 
        'close': 'close', 'volume': 'volume', 'adj close': 'close'
    }
    df = df.rename(columns=rename_map)
    
    # 중복 이름 컬럼 제거 (첫 번째 컬럼 유지)
    df = df.loc[:, ~df.columns.duplicated()]
    
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    available_cols = [c for c in required_cols if c in df.columns]
    
    return df[available_cols].apply(pd.to_numeric, errors='coerce').dropna()

def fetch_multitimeframe_data(symbol: str) -> dict:
    """종목코드를 입력받아 월봉, 일봉, 분봉 데이터를 딕셔너리로 반환"""
    clean_symbol = symbol.strip().upper()
    is_korea = clean_symbol.isdigit() and len(clean_symbol) == 6
    yf_symbol = f"{clean_symbol}.KS" if is_korea else clean_symbol
    
    data = {}
    
    try:
        # 1. 일봉 데이터 수집 (최근 1년)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        df_daily = fdr.DataReader(clean_symbol, start_date, end_date)
        data['daily'] = normalize_columns(df_daily)
        
        if data['daily'].empty:
            return {}

        # 2. 월봉 데이터 (개별 컬럼 직렬 리샘플링으로 방어)
        d = data['daily']
        df_monthly = pd.DataFrame({
            'open': d['open'].resample('ME').first(),
            'high': d['high'].resample('ME').max(),
            'low': d['low'].resample('ME').min(),
            'close': d['close'].resample('ME').last(),
            'volume': d['volume'].resample('ME').sum()
        }).dropna()
        
        data['monthly'] = df_monthly
        
        # 3. 분봉 데이터 (yfinance 이용)
        try:
            ticker = yf.Ticker(yf_symbol)
            df_15m = ticker.history(period="7d", interval="15m")
            if not df_15m.empty:
                data['intraday_15m'] = normalize_columns(df_15m)
            else:
                data['intraday_15m'] = data['daily']
        except Exception:
            data['intraday_15m'] = data['daily']
            
    except Exception as e:
        print(f"[{symbol}] 데이터 수집 오류: {e}")
        return {}
        
    return data