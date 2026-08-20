# C:\samsungAI\config.py

# 타임프레임별 스코어 가중치
WEIGHTS = {
    'monthly': 0.15,      # 월봉 (장기 추세 방향)
    'daily': 0.45,        # 일봉 (위치 / 가격 구조 / 수급)
    'intraday_60m': 0.15, # 60분/30분 (중기 파동)
    'intraday_5m': 0.15,  # 15분/5분 (단기 눌림/돌파)
    'entry_1m': 0.10      # 1분 (최종 진입 타점)
}

# NO-TRADE FILTER 설정값 (위험 종목 즉시 걸러내기)
NO_TRADE_RULES = {
    'max_daily_rsi': 80,          # 일봉 RSI 80 초과 시 추격매수 금지
    'min_clv_on_high_vol': 0.25,   # 고거래량 발생 당일 CLV 0.25 미만(윗꼬리/음봉) 금지
    'max_drop_rate': -0.07         # 당일 -7% 이상 급락 직후 매수 금지
}