# C:\samsungAI\no_trade_filter.py

import pandas as pd
from config import NO_TRADE_RULES
from feature_extractor import get_clv

def evaluate_no_trade_filter(monthly_df: pd.DataFrame, daily_df: pd.DataFrame) -> tuple[bool, list]:
    reasons = []
    
    if daily_df is None or daily_df.empty or monthly_df is None or monthly_df.empty:
        return False, ["데이터 불충분"]
        
    latest_daily = daily_df.iloc[-1]
    latest_monthly = monthly_df.iloc[-1]
    
    # 1. 월봉 20선 하회 (장기 하락 추세)
    if 'sma_20' in monthly_df.columns and latest_monthly['close'] < latest_monthly['sma_20']:
        reasons.append("월봉 20MA 하회 (장기 역배열)")
        
    # 2. 고거래량 발생 당일 저가 마감 (대량 매도 폭탄)
    clv_val = float(get_clv(daily_df).iloc[-1])
    vol_avg = daily_df['volume'].iloc[-20:].mean()
    vol_ratio = (latest_daily['volume'] / vol_avg) if vol_avg > 0 else 1.0
    
    if vol_ratio > 2.0 and clv_val < NO_TRADE_RULES['min_clv_on_high_vol']:
        reasons.append("고거래량 저가 마감 (윗트랩/매도세 출회)")
        
    # 3. 일봉 RSI 극단적 과열
    if 'rsi' in daily_df.columns and latest_daily['rsi'] > NO_TRADE_RULES['max_daily_rsi']:
        reasons.append(f"일봉 RSI 과열 ({latest_daily['rsi']:.1f} > {NO_TRADE_RULES['max_daily_rsi']})")

    # 4. 당일 -7% 이상 급락
    if len(daily_df) > 1:
        daily_return = (latest_daily['close'] - latest_daily['open']) / latest_daily['open']
        if daily_return < NO_TRADE_RULES['max_drop_rate']:
            reasons.append("일봉 장대 음봉 발생 (급락 위험)")

    return len(reasons) == 0, reasons