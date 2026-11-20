import os
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
KOTE_DIR = DATA / "kote"
DATA.mkdir(exist_ok=True)
KOTE_DIR.mkdir(exist_ok=True)

BINANCE = "https://api.binance.com"
FUTURES = "https://fapi.binance.com"
COINBASE = "https://api.exchange.coinbase.com"
KOTE = "https://kotecharts.com/api/v1"

# These IDs are published in Kote Charts' public API catalog.
KOTE_CHARTS = [
    "mvrv",
    "sopr",
    "sth-lth-sopr",
    "nupl",
    "exchange-netflow",
    "exchange-reserve",
    "fund-flows",
    "etf-flows",
    "etf-market-cap",
    "etf-flows-vs-new-supply",
    "dxy-vs-btc",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "environment-score-btc-personal-research/0.2"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def get_json(url: str, params=None, headers=None, timeout=25):
    response = SESSION.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def save_snapshot(source: str, metric: str, payload: Any, frequency: str):
    record = {
        "collected_at": utc_now(),
        "source": source,
        "metric": metric,
        "expected_frequency": frequency,
        "payload": payload,
    }
    append_jsonl(DATA / "snapshots.jsonl", record)
    return record


def collect_binance():
    out = {}
    # 4h market candles: last fully closed candle is selected.
    candles = get_json(
        f"{BINANCE}/api/v3/klines",
        {"symbol": "BTCUSDT", "interval": "4h", "limit": 3},
    )
    closed = candles[-2]
    out["btc_4h"] = {
        "open_time_ms": closed[0], "open": closed[1], "high": closed[2],
        "low": closed[3], "close": closed[4], "volume_btc": closed[5],
        "close_time_ms": closed[6], "quote_volume_usdt": closed[7],
        "trades": closed[8], "taker_buy_base": closed[9],
        "taker_buy_quote": closed[10],
        "note": "Taker buy/sell proxy from candle aggregate; not true tick-level CVD."
    }
    out["spot_price"] = get_json(f"{BINANCE}/api/v3/ticker/price", {"symbol": "BTCUSDT"})
    try:
        out["open_interest"] = get_json(f"{FUTURES}/fapi/v1/openInterest", {"symbol": "BTCUSDT"})
        out["funding_rate"] = get_json(f"{FUTURES}/fapi/v1/fundingRate", {"symbol": "BTCUSDT", "limit": 1})
        out["taker_long_short_ratio"] = get_json(
            f"{FUTURES}/futures/data/takerlongshortRatio",
            {"symbol": "BTCUSDT", "period": "4h", "limit": 2},
        )
    except Exception as exc:
        out["futures_error"] = str(exc)
    save_snapshot("binance", "market_and_derivatives_4h", out, "4h")
    return out


def collect_coinbase():
    # Coinbase candles are a second spot-market reference, not a full order-flow feed.
    data = get_json(
        f"{COINBASE}/products/BTC-USD/candles",
        {"granularity": 14400},
    )
    # Coinbase returns newest first; retain the latest few rows as received.
    payload = {"granularity_seconds": 14400, "candles": data[:3]}
    save_snapshot("coinbase", "btc_usd_4h_candles", payload, "4h")
    return payload


def collect_fred():
    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return {"status": "skipped", "reason": "FRED_API_KEY not configured"}
    series = ["VIXCLS", "DGS10", "DTWEXBGS"]
    result = {}
    for sid in series:
        result[sid] = get_json(
            "https://api.stlouisfed.org/fred/series/observations",
            {"series_id": sid, "api_key": api_key, "file_type": "json", "sort_order": "desc", "limit": 5},
        )
    # DTWEXBGS is a broad trade-weighted USD index, not ICE DXY.
    payload = {"series": result, "note": "DTWEXBGS is broad trade-weighted USD, not ICE DXY."}
    save_snapshot("fred", "macro_daily", payload, "daily")
    return payload


def collect_kote():
    api_key = os.getenv("KOTE_API_KEY", "").strip()
    if not api_key:
        return {"status": "skipped", "reason": "KOTE_API_KEY not configured"}
    headers = {"X-API-Key": api_key}
    status = {}
    for chart_id in KOTE_CHARTS:
        try:
            # Kote chart data is retained as raw JSON so series/units are not guessed.
            payload = get_json(
                f"{KOTE}/public/charts/{chart_id}",
                {"granularity": "day", "includePartial": "true"},
                headers=headers,
            )
            write_json(KOTE_DIR / f"{chart_id}.latest.json", payload)
            save_snapshot("kote_charts", chart_id, payload, "provider-defined; mostly daily")
            status[chart_id] = {"ok": True, "sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()}
        except Exception as exc:
            status[chart_id] = {"ok": False, "error": str(exc)}
        # API limit documented as 3 requests/second per key.
        time.sleep(0.4)
    return status


def main():
    report = {"collected_at": utc_now(), "version": "0.2", "sources": {}}
    for name, fn in [
        ("binance", collect_binance),
        ("coinbase", collect_coinbase),
        ("fred", collect_fred),
        ("kote_charts", collect_kote),
    ]:
        try:
            report["sources"][name] = {"ok": True, "result": fn()}
        except Exception as exc:
            report["sources"][name] = {"ok": False, "error": str(exc)}
    write_json(DATA / "latest.json", report)
    write_json(DATA / "health.json", {
        "checked_at": utc_now(),
        "version": "0.2",
        "sources": {
            name: {"ok": value.get("ok", False)}
            for name, value in report["sources"].items()
        },
    })
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
