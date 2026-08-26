import os
import sys

# 현재 main.py가 위치한 디렉터리를 Python 모듈 검색 경로 최우선(0번)에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import urllib.parse
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 상대 경로 점(.) 없이 바로 불러옵니다.
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

        if res.ok:
            data = res.json()
            items = data.get("items", [])

            if items:
                first = items[0]

                code = str(
                    first.get("code")
                    or first.get("reutersCode")
                    or ""
                ).strip().upper()

                name = str(
                    first.get("name")
                    or q
                ).strip()

                nation_code = str(
                    first.get("nationCode")
                    or ""
                ).upper()

                type_code = str(
                    first.get("typeCode")
                    or ""
                ).upper()

                # Naver 국내주식
                if nation_code == "KOR" or type_code in {
                    "KOSPI",
                    "KOSDAQ",
                    "KONEX"
                }:
                    return {
                        "code": code,
                        "name": name,
                        "is_us": False
                    }

                # 그 외 해외주식
                return {
                    "code": code,
                    "name": name,
                    "is_us": True
                }

    except Exception as e:
        print(f"[SEARCH_ERROR] {type(e).__name__}: {e}")

    # 숫자 6자리 직접 입력
    if len(q) == 6 and q.isdigit():
        return {
            "code": q,
            "name": q,
            "is_us": False
        }

    # 영문 티커만 미국주식으로 판단
    if q.isascii() and q.isalpha():
        return {
            "code": q.upper(),
            "name": q.upper(),
            "is_us": True
        }

    # 최종 fallback
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

    print(
        f"[ANALYZE_REQUEST] "
        f"code={repr(code)} "
        f"is_us={repr(is_us)}",
        flush=True
    )

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
        print(
            f"[ENGINE_CALL] "
            f"code={repr(clean)}, "
            f"is_us={repr(is_us)}",
            flush=True
        )

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