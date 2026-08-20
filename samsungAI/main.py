# C:\samsungAI\main.py

from service import analyze_stock_for_api
import json

def main():
    target_symbols = ["005930", "000660", "AAPL"]
    print("=== samsungAI 파이프라인 분석 시작 ===")
    
    for symbol in target_symbols:
        res = analyze_stock_for_api(symbol)
        print(f"\n[종목: {symbol}] -> 상태: {res.get('status')}, 점수: {res.get('final_score')}")
        if not res.get('trade_allowed'):
            print(f"  └ 거절 사유: {res.get('reasons')}")

if __name__ == "__main__":
    main()