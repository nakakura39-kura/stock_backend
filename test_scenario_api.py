import requests
import json

BASE_URL = "http://127.0.0.1:8000"
ENDPOINT = "/api/v1/stock/scenario"

payload = {
    "symbol": "삼성전자"
}

headers = {
    "Content-Type": "application/json"
}

def test_predict_scenario():
    url = f"{BASE_URL}{ENDPOINT}"
    print(f"🚀 API 요청 전송: {url}")
    print(f"📦 요청 데이터: {payload}\n")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        print(f"응답 상태 코드: {response.status_code}")

        if response.status_code == 200:
            res_data = response.json()
            print("\n✅ 시나리오 예측 API 호출 성공!")
            print("=" * 50)
            print(f"변환된 종목 코드: {res_data.get('symbol')}")
            
            data = res_data.get("data", {})
            print(f"유사 패턴 매칭 건수: {data.get('matched_count')}건")
            print(f"예측 신뢰도: {data.get('prediction_confidence')}%")
            print("-" * 50)
            
            for scenario in data.get("scenarios", []):
                print(f"[{scenario['rank']}순위] {scenario['name']}")
                print(f"  • 발생 확률: {scenario['probability']}%")
                print(f"  • D+5 목표 수익률: {scenario['final_return']}")
                print(f"  • 5일간 예상 경로(%): {scenario['path']}")
                print()
            print("=" * 50)
        else:
            print(f"❌ 요청 실패 ({response.status_code}):")
            print(response.text)

    except Exception as e:
        print(f"❌ 예외 발생: {str(e)}")

if __name__ == "__main__":
    test_predict_scenario()