"""Settings read from the environment, with .env at the repo root loaded first.

Each model has its own API key and an optional base URL, since each model may be served
from a separate key or endpoint. GEMINI_API_KEY is used for any model without its own key.
"""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class ModelSettings:
    name: str
    model: str
    api_key: str
    base_url: str


def model_settings(name: str, default_model: str) -> ModelSettings:
    """name is the env prefix, e.g. HYDROGEN reads HYDROGEN_API_KEY, HYDROGEN_MODEL, HYDROGEN_BASE_URL."""
    return ModelSettings(
        name=name,
        model=os.environ.get(f"{name}_MODEL") or default_model,
        api_key=os.environ.get(f"{name}_API_KEY") or os.environ.get("GEMINI_API_KEY", ""),
        base_url=os.environ.get(f"{name}_BASE_URL", ""),
    )


HYDROGEN = model_settings("HYDROGEN", "gemini-4-hydrogen")
DECISIONS = model_settings("DECISIONS", "gemini-decision-1")

DATA_DIR = ROOT / os.environ.get("DATA_DIR", "data")
RUNS_DIR = DATA_DIR / "runs"
NPC_DIR = DATA_DIR / "npcs"

# Markets with downloaded price history (scripts/download_prices.py). Anything else is tested on BTC.
TESTABLE_MARKETS = ["BTC-USD", "ETH-USD", "SOL-USD"]
DEFAULT_TEST_MARKET = "BTC-USD"
TIMEFRAMES = ["5m", "1h", "1d"]  # candle files scripts/download_prices.py can fetch

# Scanner: a segment gets a flag when the Decisions API's yes probability reaches this.
SCAN_THRESHOLD = float(os.environ.get("SCAN_THRESHOLD", "0.5"))
# Matcher: a new strategy joins an existing NPC at or above this "same strategy" probability.
MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.9"))
MATCH_CANDIDATES = 3
