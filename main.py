import os
import urllib.parse
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend_pipeline import MultiTimeframePatternEngine

app = FastAPI(title="Stock AI Multi-Timeframe Chart Analyzer", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/"
}
engine = MultiTimeframePatternEngine(forecast_horizon=5, top_k=50)

def normalize_code(code: str, is_us: bool) -> str:
    val = code.strip().upper()
    if not is_us and val.startswith("A") and len(val) == 7 and val[1:].isdigit():
        val = val[1:]
    # 중복 .KS/.KQ 결합 방지를 위해 클리닝만 수행
    val = val.replace(".KS", "").replace(".KQ", "")
    return val

def search_naver(q: str):
    if not q:
        return {"code": "005930", "name": "삼성전자", "is_us": False}
        
    try:
        url = f"https://ac.stock.naver.com/ac?q={urllib.parse.quote(q)}&target=stock"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.ok:
            items = res.json().get("items", [])
            if items:
                first = items[0]
                market = first[2] if len(first) > 2 else ""
                is_us = market.upper() in ["NASDAQ", "NYSE", "AMEX"]
                return {"code": first[0], "name": first[1], "is_us": is_us}
    except Exception as e:
        print("Search error:", e)
    
    if q.isalpha():
        return {"code": q.upper(), "name": q.upper(), "is_us": True}
    return {"code": q, "name": q, "is_us": False}

@app.get("/")
def root():
    return {"status": "ok", "version": "2.1.0"}

@app.get("/search")
@app.get("/api/search")
def search_stock(query: str = Query("", alias="query")):
    return search_naver(query.strip())

@app.get("/analyze")
@app.get("/api/analyze")
def analyze_stock(
    code: str = Query("", alias="code"), 
    is_us: bool = Query(False, alias="is_us")
):
    if not code.strip():
        raise HTTPException(status_code=400, detail="Code parameter is required.")
    
    clean = normalize_code(code, is_us)
    
    try:
        # backend_pipeline 내부의 fetcher를 통해 조회
        daily = engine.fetch_daily(clean, is_us, "5y")

        if daily is None or daily.empty:
            print(f"[DATA_ERROR] Ticker '{clean}' data fetch failed. (is_us={is_us})")
            return JSONResponse(
                status_code=404, 
                content={"error": f"'{clean}' 종목의 주가 데이터를 수집하지 못했습니다."}
            )

        monthly = engine.fetch_monthly(clean, is_us, "10y")
        h60 = engine.fetch_intraday(clean, is_us, "60m")
        m15 = engine.fetch_intraday(clean, is_us, "15m")

        result = engine.analyze(daily, monthly, h60, m15)
        
        return {
            "ticker": clean,
            "is_us": is_us,
            "price": result.get("currentPrice", 0.0),
            "analysis": result
        }
        
    except Exception as e:
        print(f"[ENGINE_ERROR] {e}")
        return JSONResponse(
            status_code=500, 
            content={"error": f"AI 분석 연산 중 오류가 발생했습니다: {str(e)}"}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)