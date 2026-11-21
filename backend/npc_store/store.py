"""NPC library: JSON files under DATA_DIR (gitignored), shared by the pipeline and the API.

    data/npcs/<npc_id>.json              one NPC record (schemas/npc_record.json)
    data/npcs/<npc_id>_trades.json       its trades for Simulate (schemas/trades.json)
    data/strategies/<strategy_id>.json   one strategy rules record (schemas/strategy_rules.json)

Strategies are saved as soon as they are extracted, before any NPC is born, so the Matcher can
compare a new video against every strategy seen so far.

Two ways to use it, over the same files:
- Module functions for the API and scripts (Person 3): save_npc(record, trades), list_npcs(),
  get_npc(id), get_trades(id), find_by_url(url), normalize_url(url).
- The Store class for the pipeline and tests, which can point at another folder: Store(root).
"""

import json
from pathlib import Path

from backend.config import DATA_DIR  # also loads .env, so the API sees GEMINI_API_KEY
from backend.watcher.watcher import video_id


def normalize_url(url: str) -> str:
    """Reduce YouTube links to their video id so watch?v=, youtu.be and shorts match."""
    try:
        return video_id(url)
    except ValueError:
        return url.strip()


def _source_url(source) -> str:
    return source.get("url", "") if isinstance(source, dict) else str(source)


class Store:
    def __init__(self, root: Path = DATA_DIR):
        self.npc_dir = Path(root) / "npcs"
        self.strategy_dir = Path(root) / "strategies"

    # --- reading ---
    @staticmethod
    def _read_all(folder: Path) -> list[dict]:
        if not folder.exists():
            return []
        return [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))
                if not p.name.endswith("_trades.json")]

    def npcs(self) -> list[dict]:
        return self._read_all(self.npc_dir)

    def strategies(self) -> list[dict]:
        return self._read_all(self.strategy_dir)

    def get_npc(self, npc_id: str) -> dict | None:
        p = self.npc_dir / f"{npc_id}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def get_trades(self, npc_id: str) -> dict | None:
        rec = self.get_npc(npc_id)
        if not rec or not rec.get("trades_path"):
            return None
        p = Path(rec["trades_path"])
        return json.loads(p.read_text()) if p.exists() else None

    def get_strategy(self, strategy_id: str) -> dict | None:
        p = self.strategy_dir / f"{strategy_id}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def npc_for_video(self, url: str) -> dict | None:
        """Same-link matching: a plain lookup that must always work."""
        vid = normalize_url(url)
        for npc in self.npcs():
            if any(normalize_url(_source_url(s)) == vid for s in npc.get("source_videos", [])):
                return npc
        return None

    def strategy_for_video(self, url: str) -> dict | None:
        vid = normalize_url(url)
        for strategy in self.strategies():
            if any(normalize_url(s["url"]) == vid for s in strategy.get("source_videos", [])):
                return strategy
        return None

    def npc_for_strategy(self, strategy_id: str) -> dict | None:
        return next((n for n in self.npcs() if n.get("strategy_id") == strategy_id), None)

    # --- writing ---
    @staticmethod
    def _write(path: Path, record: dict, indent: int | None = 2) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=indent))
        tmp.replace(path)

    def save_npc(self, record: dict, trades: dict | None = None) -> dict:
        """Save an NPC record (and its trades, if given). Returns the record."""
        if trades is not None:
            trades_path = self.npc_dir / f"{record['npc_id']}_trades.json"
            self._write(trades_path, trades, indent=None)
            record["trades_path"] = str(trades_path)
        self._write(self.npc_dir / f"{record['npc_id']}.json", record)
        return record

    def save_strategy(self, rules: dict) -> None:
        self._write(self.strategy_dir / f"{rules['strategy_id']}.json", rules)

    def detach_video(self, url: str, keep_strategy_id: str) -> None:
        """Remove a video from every other strategy, e.g. after it's re-extracted with new wording.

        A strategy left with no videos is deleted, unless an NPC was already born from it.
        """
        vid = normalize_url(url)
        for strategy in self.strategies():
            sid = strategy["strategy_id"]
            sources = strategy.get("source_videos", [])
            remaining = [v for v in sources if normalize_url(v["url"]) != vid]
            if sid == keep_strategy_id or len(remaining) == len(sources):
                continue
            path = self.strategy_dir / f"{sid}.json"
            if remaining or self.npc_for_strategy(sid) is not None:
                self._write(path, {**strategy, "source_videos": remaining})
            else:
                path.unlink()

    def add_source_video(self, strategy_id: str, source: dict) -> None:
        """Attach another video to an existing strategy and its NPC, if it isn't there already."""
        vid = normalize_url(source["url"])
        rules = self.get_strategy(strategy_id)
        if rules is not None and all(normalize_url(s["url"]) != vid for s in rules["source_videos"]):
            rules["source_videos"].append(source)
            self.save_strategy(rules)
        npc = self.npc_for_strategy(strategy_id)
        if npc is not None and all(normalize_url(_source_url(s)) != vid for s in npc.get("source_videos", [])):
            npc.setdefault("source_videos", []).append(source)
            self.save_npc(npc)


# Module functions over the default library, used by the API and scripts.
_default = Store()


def save_npc(record: dict, trades: dict | None = None) -> dict:
    return _default.save_npc(record, trades)


def list_npcs() -> list[dict]:
    return _default.npcs()


def get_npc(npc_id: str) -> dict | None:
    return _default.get_npc(npc_id)


def get_trades(npc_id: str) -> dict | None:
    return _default.get_trades(npc_id)


def find_by_url(url: str) -> dict | None:
    return _default.npc_for_video(url)
