# Environment Score BTC Collector v0.2

Personal research collector. It gathers source data; it does **not** calculate a trading score or issue trading signals.

## What's included
- Binance BTCUSDT spot price and last fully closed 4h candle.
- Binance Futures open interest, latest funding rate, and taker long/short ratio (where endpoints are accessible).
- Coinbase BTC-USD 4h candles as a second spot reference.
- Optional FRED daily macro series: VIXCLS, DGS10, DTWEXBGS.
- Kote Charts daily chart payloads for on-chain metrics, exchange flows/reserves, fund flows, spot ETF flows/holdings, ETF flows vs issuance, and BTC vs dollar index.

Kote chart responses are stored raw under `data/kote/` and in `data/snapshots.jsonl`. Raw storage is intentional: the collector does not guess units or series names. The Kote methodology endpoint/catalog should be used when building normalization and score calculations.

## Important frequency notes
- Workflow runs every 4 hours (UTC).
- Binance/Coinbase market data is collected on each run.
- Kote chart data is requested on each run, but many Kote series update daily; some flow metrics may update after blocks. Repeated identical daily values are not new observations.
- ETF net flows are daily and may be revised/settled with a delay. Do not treat four polls per day as four independent ETF observations.
- FRED series are daily and may publish with a delay.
- `DTWEXBGS` is a broad trade-weighted dollar index, **not** ICE DXY.
- Candle-derived taker buy/sell values are a proxy, **not** true tick-level Spot CVD.

## GitHub Actions secrets
Add these in repository Settings -> Secrets and variables -> Actions:
- `KOTE_API_KEY` (recommended): create a free Kote Charts account/API key. Personal non-commercial use requires attribution to Kote Charts.
- `FRED_API_KEY` (optional): free FRED API key. Without it, macro collection is skipped.

Never put API keys directly in source code or commit them to the repository.

## Run locally
```bash
pip install -r requirements.txt
# Set KOTE_API_KEY and optionally FRED_API_KEY in your environment
python main.py
```

## Current limitations / next stage
- No Environment Score, Bias, Confidence, or Fragility calculation yet.
- No historical backtest or calibrated weights yet.
- Kote responses are retained raw; next development step is to inspect a real authenticated response, map exact fields/units/cadence, and build normalized daily series with deduplication.
- This collector has only passed a syntax check in this build environment. A successful live run requires adding API keys and testing from GitHub Actions.
