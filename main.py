import os
import urllib.parse
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend_pipeline import MultiTimeframePatternEngine

app = FastAPI(
    title="Stock AI Multi-Timeframe Chart Analyzer",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/"
}

engine = MultiTimeframePatternEngine(
    forecast_horizon=5,
    top_k=50
)


def normalize_code(code: str, is_us: bool) -> str:
    val = code.strip().upper()

    if not is_us and val.startswith("A") and len(val) == 7 and val[1:].isdigit():
        val = val[1:]

    val = val.replace(".KS", "").replace(".KQ", "")

    return val


def search_naver(q: str):
    """
    종목 검색

    한국:
        삼성전자 → 005930 / False

    미국:
        AAPL → AAPL / True
    """

    q = q.strip()

    if not q:
        return {
            "code": "005930",
            "name": "삼성전자",
            "is_us": False
        }

    try:
        url = (
            "https://ac.stock.naver.com/ac"
            f"?q={urllib.parse.quote(q)}"
            "&target=stock"
        )

        res = requests.get(
            url,
            headers=HEADERS,
            timeout=5
        )

        print(f"[SEARCH] query={q}")
        print(f"[SEARCH] status={res.status_code}")

        if res.ok:

            # ★ 실제 Naver 응답 확인용
            print(f"[NAVER_RAW] {res.text[:3000]}")

            data = res.json()
            items = data.get("items", [])

            print(f"[NAVER_ITEMS] {items}")

            if items:

                first = items[0]

                print(f"[NAVER_FIRST] {first}")

                # -----------------------------------
                # 배열 형태
                # -----------------------------------
                if isinstance(first, list):

                    values = [
                        str(x).strip()
                        for x in first
                    ]

                    print(f"[NAVER_VALUES] {values}")

                    # 6자리 숫자 코드 찾기
                    stock_code = next(
                        (
                            x for x in values
                            if len(x) == 6
                            and x.isdigit()
                        ),
                        None
                    )

                    if stock_code:

                        stock_name = next(
                            (
                                x for x in values
                                if x == q
                            ),
                            q
                        )

                        print(
                            f"[SEARCH_RESULT] "
                            f"KR {stock_name} -> {stock_code}"
                        )

                        return {
                            "code": stock_code,
                            "name": stock_name,
                            "is_us": False
                        }

                # -----------------------------------
                # 객체 형태
                # -----------------------------------
                elif isinstance(first, dict):

                    code = (
                        first.get("code")
                        or first.get("symbol")
                        or first.get("ticker")
                    )

                    name = (
                        first.get("name")
                        or first.get("stockName")
                        or first.get("title")
                        or q
                    )

                    market = str(
                        first.get("market")
                        or first.get("exchange")
                        or ""
                    ).upper()

                    if code:

                        code = str(code).strip()

                        # 6자리 숫자는 무조건 한국
                        if (
                            len(code) == 6
                            and code.isdigit()
                        ):
                            return {
                                "code": code,
                                "name": str(name),
                                "is_us": False
                            }

                        is_us = market in {
                            "NASDAQ",
                            "NYSE",
                            "AMEX",
                            "NYSEARCA",
                            "ARCA"
                        }

                        return {
                            "code": code.upper(),
                            "name": str(name),
                            "is_us": is_us
                        }

    except Exception as e:

        print(
            f"[SEARCH_ERROR] "
            f"{type(e).__name__}: {e}"
        )

    # -----------------------------------
    # 직접 입력한 한국 종목코드
    # -----------------------------------

    if len(q) == 6 and q.isdigit():

        return {
            "code": q,
            "name": q,
            "is_us": False
        }

    # -----------------------------------
    # 미국 티커
    #
    # ★ isascii()가 중요
    # -----------------------------------

    if q.isascii() and q.isalpha():

        return {
            "code": q.upper(),
            "name": q.upper(),
            "is_us": True
        }

    # -----------------------------------
    # 최종 fallback
    # -----------------------------------

    return {
        "code": q,
        "name": q,
        "is_us": False
    }


@app.get("/")
def root():
    return {
        "status": "ok",
        "version": "2.1.0"
    }


@app.get("/search")
@app.get("/api/search")
def search_stock(
    query: str = Query("", alias="query")
):
    return search_naver(query.strip())


@app.get("/analyze")
@app.get("/api/analyze")
def analyze_stock(
    code: str = Query("", alias="code"),
    is_us: bool = Query(False, alias="is_us")
):

    if not code.strip():
        raise HTTPException(
            status_code=400,
            detail="Code parameter is required."
        )

    clean = normalize_code(code, is_us)

    print(
        f"[ANALYZE] "
        f"code={code}, "
        f"clean={clean}, "
        f"is_us={is_us}"
    )

    try:

        daily = engine.fetch_daily(
            clean,
            is_us,
            "5y"
        )

        if daily is None or daily.empty:

            print(
                f"[DATA_ERROR] "
                f"Ticker '{clean}' "
                f"data fetch failed. "
                f"(is_us={is_us})"
            )

            return JSONResponse(
                status_code=404,
                content={
                    "error":
                        f"'{clean}' 종목의 "
                        f"주가 데이터를 수집하지 못했습니다."
                }
            )

        monthly = engine.fetch_monthly(
            clean,
            is_us,
            "10y"
        )

        h60 = engine.fetch_intraday(
            clean,
            is_us,
            "60m"
        )

        m15 = engine.fetch_intraday(
            clean,
            is_us,
            "15m"
        )

        result = engine.analyze(
            daily,
            monthly,
            h60,
            m15
        )

        return {
            "ticker": clean,
            "is_us": is_us,
            "price": result.get(
                "currentPrice",
                0.0
            ),
            "analysis": result
        }

    except Exception as e:

        print(
            f"[ENGINE_ERROR] "
            f"{type(e).__name__}: {e}"
        )

        return JSONResponse(
            status_code=500,
            content={
                "error":
                    f"AI 분석 연산 중 오류가 발생했습니다: {str(e)}"
            }
        )


if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            8000
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )