"""Download full-history crypto candles from Coinbase Exchange's public API.

No API key needed. Output goes to data/prices/<SYMBOL>_<interval>.csv (gitignored).

Usage:
    python3 scripts/download_prices.py                       # BTC, ETH, SOL daily
    python3 scripts/download_prices.py --interval 1h
    python3 scripts/download_prices.py --symbols BTC-USD --start 2024-01-01
"""

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.exchange.coinbase.com/products/{symbol}/candles"
GRANULARITY = {"1d": 86400, "1h": 3600}
MAX_CANDLES = 300  # Coinbase returns at most 300 candles per request
DEFAULT_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD"]
EARLIEST = "2015-07-20"  # Coinbase Exchange launch; empty windows before a coin lists are skipped


def fetch(symbol: str, granularity: int, start: datetime, end: datetime) -> list:
    url = (
        f"{API.format(symbol=symbol)}?granularity={granularity}"
        f"&start={start.isoformat()}&end={end.isoformat()}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "guru-check-price-downloader"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"Gave up on {url}")


def download(symbol: str, interval: str, start: datetime, out_dir: Path) -> Path:
    granularity = GRANULARITY[interval]
    step = timedelta(seconds=granularity * MAX_CANDLES)
    now = datetime.now(timezone.utc)
    rows = {}
    cursor = start
    while cursor < now:
        window_end = min(cursor + step, now)
        for t, low, high, open_, close, volume in fetch(symbol, granularity, cursor, window_end):
            rows[t] = (open_, high, low, close, volume)
        cursor = window_end
        time.sleep(0.15)  # stay under the public rate limit

    out_path = out_dir / f"{symbol}_{interval}.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "date", "open", "high", "low", "close", "volume"])
        for t in sorted(rows):
            date = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([t, date, *rows[t]])
    print(f"{symbol} {interval}: {len(rows)} candles -> {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--interval", choices=GRANULARITY, default="1d")
    parser.add_argument("--start", default=EARLIEST, help="YYYY-MM-DD, default full history")
    parser.add_argument("--out", default="data/prices")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    for symbol in args.symbols:
        download(symbol, args.interval, start, out_dir)


if __name__ == "__main__":
    main()
