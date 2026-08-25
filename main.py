import urllib.parse
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend_pipeline import MultiTimeframePatternEngine

app = FastAPI(title="Stock AI Multi-Timeframe Chart Analyzer", version="2.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}
engine = MultiTimeframePatternEngine(forecast_horizon=5, top_k=50)

# 미국 티커 앞의 'A' prefix 처리 및 규격화
def normalize_code(code: str, is_us: bool) -> str:
    val = code.strip().upper()
    if not is_us and val.startswith("A") and len(val) == 7 and val[1:].isdigit():
        val = val[1:]
    val = val.replace(".KS", "").replace(".KQ", "")
    return val

def search_naver(q: str):
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
def analyze_stock(code: str = Query("", alias="code"), is_us: bool = Query(False, alias="is_us")):
    if not code.strip():
        raise HTTPException(status_code=400, detail="Code parameter is required.")
    
    clean = normalize_code(code, is_us)
    daily = engine.fetch_daily(clean, is_us, "5y")
    
    # 데이터 로드 실패 시 가짜 데이터 생성 없이 깔끔하게 에러 반환
    if daily.empty:
        return JSONResponse(status_code=503, content={"error": "주가 데이터를 불러올 수 없습니다.", "ticker": clean})

    monthly = engine.fetch_monthly(clean, is_us, "10y")
    h60 = engine.fetch_intraday(clean, is_us, "60m")
    m15 = engine.fetch_intraday(clean, is_us, "15m")

    result = engine.analyze(daily, monthly, h60, m15)
    return {
        "ticker": clean,
        "isUs": is_us,
        "price": result["currentPrice"],
        "analysis": result
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)