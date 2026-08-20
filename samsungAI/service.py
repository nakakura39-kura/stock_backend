# C:\samsungAI\service.py

import json
from data_loader import fetch_multitimeframe_data
from indicators import add_technical_indicators
from feature_extractor import get_clv, check_abcd_pullback
from no_trade_filter import evaluate_no_trade_filter
from scorer import calculate_total_score

def analyze_stock_for_api(symbol: str) -> dict:
    """FastAPI 및 백엔드 서버 연동용 핵심 분석 서비스 엔드포인트"""
    # 1. 데이터 수집
    raw_data = fetch_multitimeframe_data(symbol)
    if not raw_data or 'daily' not in raw_data or raw_data['daily'].empty:
        return {"error": "데이터를 불러올 수 없습니다.", "symbol": symbol}
        
    # 2. 기술적 지표 생성
    m_df = add_technical_indicators(raw_data['monthly'])
    d_df = add_technical_indicators(raw_data['daily'])
    
    # 3. NO-TRADE FILTER 검사 (최우선)
    is_safe, reject_reasons = evaluate_no_trade_filter(m_df, d_df)
    latest_price = float(d_df['close'].iloc[-1])
    
    if not is_safe:
        return {
            "symbol": symbol,
            "status": "REJECTED",
            "trade_allowed": False,
            "reasons": reject_reasons,
            "final_score": 0,
            "current_price": latest_price,
            "target_price": round(latest_price * 1.05, 2),
            "stop_loss_price": round(latest_price * 0.95, 2)
        }
        
    # 4. 피처 추출 및 타임프레임별 스코어 계산
    pullback = check_abcd_pullback(d_df)
    clv_val = float(get_clv(d_df).iloc[-1])
    
    daily_score = min(100, max(0, 50 + (clv_val * 30) + (20 if pullback['is_pullback'] else 0)))
    monthly_score = 85 if ('sma_20' in m_df.columns and m_df['close'].iloc[-1] > m_df['sma_20'].iloc[-1]) else 35
    
    scores = {
        'monthly': monthly_score,
        'daily': daily_score,
        'intraday_60m': 70,
        'intraday_5m': 75,
        'entry_1m': 80
    }
    
    score_result = calculate_total_score(scores)
    
    # 5. 최종 API 결과 반환
    return {
        "symbol": symbol,
        "status": "APPROVED",
        "trade_allowed": True,
        "final_score": score_result['final_score'],
        "score_breakdown": score_result['breakdown'],
        "current_price": latest_price,
        "target_price": round(latest_price * 1.08, 2),
        "stop_loss_price": round(latest_price * 0.96, 2),
        "clv": round(clv_val, 2),
        "is_pullback": pullback['is_pullback']
    }

if __name__ == "__main__":
    # 삼성전자(005930) 테스트 실행
    result = analyze_stock_for_api("005930")
    print(json.dumps(result, indent=4, ensure_ascii=False))