"""File-based NPC library under data/ (gitignored).

    data/npcs/<npc_id>.json             one NPC record (schemas/npc_record.json)
    data/strategies/<strategy_id>.json  one strategy rules record (schemas/strategy_rules.json)

Strategies are saved as soon as they are extracted, before any NPC is born, so the Matcher can
compare a new video against every strategy seen so far.
"""

import json
from pathlib import Path

from backend.config import DATA_DIR
from backend.watcher.watcher import video_id


class Store:
    def __init__(self, root: Path = DATA_DIR):
        self.npc_dir = Path(root) / "npcs"
        self.strategy_dir = Path(root) / "strategies"

    # --- reading ---
    @staticmethod
    def _read_all(folder: Path) -> list[dict]:
        if not folder.exists():
            return []
        return [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]

    def npcs(self) -> list[dict]:
        return self._read_all(self.npc_dir)

    def strategies(self) -> list[dict]:
        return self._read_all(self.strategy_dir)

    def npc_for_video(self, url: str) -> dict | None:
        vid = video_id(url)
        for npc in self.npcs():
            for source in npc.get("source_videos", []):
                try:
                    if video_id(source["url"] if isinstance(source, dict) else source) == vid:
                        return npc
                except ValueError:
                    continue
        return None

    def strategy_for_video(self, url: str) -> dict | None:
        vid = video_id(url)
        for strategy in self.strategies():
            if any(video_id(s["url"]) == vid for s in strategy.get("source_videos", [])):
                return strategy
        return None

    def npc_for_strategy(self, strategy_id: str) -> dict | None:
        return next((n for n in self.npcs() if n.get("strategy_id") == strategy_id), None)

    # --- writing ---
    @staticmethod
    def _write(path: Path, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=2))
        tmp.replace(path)

    def save_strategy(self, rules: dict) -> None:
        self._write(self.strategy_dir / f"{rules['strategy_id']}.json", rules)

    def detach_video(self, url: str, keep_strategy_id: str) -> None:
        """Remove a video from every other strategy, e.g. after it's re-extracted with new wording.

        A strategy left with no videos is deleted, unless an NPC was already born from it.
        """
        vid = video_id(url)
        for strategy in self.strategies():
            sid = strategy["strategy_id"]
            sources = strategy.get("source_videos", [])
            remaining = [v for v in sources if video_id(v["url"]) != vid]
            if sid == keep_strategy_id or len(remaining) == len(sources):
                continue
            path = self.strategy_dir / f"{sid}.json"
            if remaining or self.npc_for_strategy(sid) is not None:
                self._write(path, {**strategy, "source_videos": remaining})
            else:
                path.unlink()

    def save_npc(self, npc: dict) -> None:
        self._write(self.npc_dir / f"{npc['npc_id']}.json", npc)

    def add_source_video(self, strategy_id: str, source: dict) -> None:
        """Attach another video to an existing strategy and its NPC, if it isn't there already."""
        path = self.strategy_dir / f"{strategy_id}.json"
        if path.exists():
            rules = json.loads(path.read_text())
            if all(video_id(s["url"]) != video_id(source["url"]) for s in rules["source_videos"]):
                rules["source_videos"].append(source)
                self._write(path, rules)
        npc = self.npc_for_strategy(strategy_id)
        if npc is not None:
            urls = [s["url"] if isinstance(s, dict) else s for s in npc.get("source_videos", [])]
            if all(video_id(u) != video_id(source["url"]) for u in urls):
                npc.setdefault("source_videos", []).append(source)
                self.save_npc(npc)
