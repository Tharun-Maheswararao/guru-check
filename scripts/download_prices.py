"""Download full-history crypto candles from Coinbase Exchange's public API.

No API key needed. Output goes to data/prices/<SYMBOL>_<interval>.csv (gitignored).
Rows are appended as they arrive, and a rerun continues from the last saved candle, so a long
download (5m is about 4,000 requests per coin) can be stopped and resumed.

Usage:
    python3 scripts/download_prices.py                       # BTC, ETH, SOL daily
    python3 scripts/download_prices.py --interval 1h
    python3 scripts/download_prices.py --interval 5m         # about 10-20 minutes per coin
    python3 scripts/download_prices.py --symbols BTC-USD --start 2024-01-01
    python3 scripts/download_prices.py --fresh                # discard saved files and start over
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
GRANULARITY = {"5m": 300, "1h": 3600, "1d": 86400}
MAX_CANDLES = 300  # Coinbase returns at most 300 candles per request
DEFAULT_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD"]
EARLIEST = "2015-07-20"  # first Coinbase candle; empty windows before a coin lists are skipped
HEADER = ["timestamp", "date", "open", "high", "low", "close", "volume"]


def fetch(symbol: str, granularity: int, start: datetime, end: datetime) -> list:
    url = (
        f"{API.format(symbol=symbol)}?granularity={granularity}"
        f"&start={start.isoformat()}&end={end.isoformat()}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "guru-check-price-downloader"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise
        except urllib.error.URLError:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Gave up on {url}")


def last_saved_timestamp(path: Path) -> int | None:
    """Timestamp of the last row in an existing CSV, or None if there isn't one."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open("rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 4096))
        lines = f.read().decode().strip().splitlines()
    last = lines[-1].split(",")[0] if lines else ""
    return int(last) if last.isdigit() else None


def download(symbol: str, interval: str, start: datetime, out_dir: Path, fresh: bool = False) -> Path:
    granularity = GRANULARITY[interval]
    step = timedelta(seconds=granularity * MAX_CANDLES)
    out_path = out_dir / f"{symbol}_{interval}.csv"
    if fresh and out_path.exists():
        out_path.unlink()

    last = last_saved_timestamp(out_path)
    if last is not None:
        start = max(start, datetime.fromtimestamp(last + granularity, timezone.utc))
        print(f"{symbol} {interval}: resuming after {datetime.fromtimestamp(last, timezone.utc):%Y-%m-%d %H:%M}")
    else:
        with out_path.open("w", newline="") as f:
            csv.writer(f).writerow(HEADER)
        last = -1

    now = datetime.now(timezone.utc)
    total_requests = max(1, int((now - start) / step) + 1)
    written, requests, cursor = 0, 0, start
    with out_path.open("a", newline="") as f:
        writer = csv.writer(f)
        while cursor < now:
            window_end = min(cursor + step, now)
            rows = sorted(fetch(symbol, granularity, cursor, window_end), key=lambda r: r[0])
            for t, low, high, open_, close, volume in rows:
                if t > last:  # windows share edges; never write a candle twice
                    date = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    writer.writerow([t, date, open_, high, low, close, volume])
                    last, written = t, written + 1
            cursor = window_end
            requests += 1
            if requests % 200 == 0:
                f.flush()
                print(f"  {symbol} {interval}: {requests}/{total_requests} requests, at {cursor:%Y-%m-%d}")
            time.sleep(0.15)  # stay under the public rate limit

    print(f"{symbol} {interval}: {written} new candles -> {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--interval", choices=GRANULARITY, default="1d")
    parser.add_argument("--start", default=EARLIEST, help="YYYY-MM-DD, default full history")
    parser.add_argument("--out", default="data/prices")
    parser.add_argument("--fresh", action="store_true", help="discard saved files and start over")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    for symbol in args.symbols:
        download(symbol, args.interval, start, out_dir, fresh=args.fresh)


if __name__ == "__main__":
    main()
