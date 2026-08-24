import urllib.parse
import requests
import numpy as np
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend_pipeline import MultiTimeframePatternEngine

app = FastAPI(title="Stock AI Chart Analyzer", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}
STOCK_MAP = {
    "삼성전자": {"code": "005930", "name": "삼성전자", "is_us": False},
    "SK하이닉스": {"code": "000660", "name": "SK하이닉스", "is_us": False},
    "네이버": {"code": "035420", "name": "NAVER", "is_us": False},
    "NAVER": {"code": "035420", "name": "NAVER", "is_us": False},
    "TSLA": {"code": "TSLA", "name": "테슬라", "is_us": True},
    "AAPL": {"code": "AAPL", "name": "애플", "is_us": True},
    "NVDA": {"code": "NVDA", "name": "엔비디아", "is_us": True},
    "RXRX": {"code": "RXRX", "name": "Recursion Pharma", "is_us": True},
}
engine = MultiTimeframePatternEngine(forecast_horizon=5, top_k=50)


def normalize_code(code: str, is_us: bool) -> str:
    value = code.strip().upper()
    if not is_us and value.startswith("A") and len(value) == 7 and value[1:].isdigit():
        value = value[1:]
    value = value.replace(".KS", "").replace(".KQ", "")
    return value


def search_name(q: str):
    if not q:
        return STOCK_MAP["삼성전자"]
    for k, v in STOCK_MAP.items():
        if q.lower() == k.lower():
            return v
    if q.isalpha() and len(q) <= 5:
        return {"code": q.upper(), "name": q.upper(), "is_us": True}
    if q.isdigit() and len(q) == 6:
        return {"code": q, "name": q, "is_us": False}
    try:
        url = f"https://ac.stock.naver.com/ac?q={urllib.parse.quote(q)}&target=stock"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.ok:
            items = res.json().get("items", [])
            if items:
                first = items[0]
                market = first[2] if len(first) > 2 else ""
                return {"code": first[0], "name": first[1], "is_us": market.upper() in ["NASDAQ", "NYSE", "AMEX"]}
    except Exception as e:
        print("Search error:", e)
    raise HTTPException(status_code=404, detail="종목을 찾지 못했습니다.")


@app.get("/")
def root():
    return {"status": "ok", "message": "Stock AI Chart Analyzer Active", "version": "2.0.0"}


@app.get("/search")
@app.get("/api/search")
def search_stock(query: str = Query("", alias="query")):
    return search_name(query.strip())


@app.get("/stock-price")
@app.get("/api/stock-price")
def get_stock_price(code: str = Query("", alias="code"), is_us: bool = Query(False, alias="is_us")):
    if not code.strip():
        return JSONResponse(status_code=400, content={"error": "Code is required"})
    clean = normalize_code(code, is_us)
    daily = engine.fetch_daily(clean, is_us, "5y")
    if daily.empty:
        return JSONResponse(status_code=503, content={"error": "주가 데이터를 가져오지 못했습니다.", "ticker": clean})
    monthly = engine.fetch_monthly(clean, is_us, "10y")
    h60 = engine.fetch_intraday(clean, is_us, "60m")
    m15 = engine.fetch_intraday(clean, is_us, "15m")
    result = engine.analyze(daily, monthly, h60, m15)
    return {
        "ticker": clean,
        "priceList": [{"localTradedAt": str(daily.index[-1]), "closePrice": str(result["currentPrice"]), "stockName": clean, "isUs": is_us}],
        "aiPrediction": result["scenario"],
        "analysis": result,
    }


@app.get("/analyze")
@app.get("/api/analyze")
def analyze_stock(code: str = Query("", alias="code"), is_us: bool = Query(False, alias="is_us")):
    return get_stock_price(code, is_us)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
