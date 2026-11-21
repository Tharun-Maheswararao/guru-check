"""NPC store: one JSON record per NPC plus one trades file, under DATA_DIR/npcs (gitignored).

Record shape: schemas/npc_record.json. Trades shape: schemas/trades.json.
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
NPC_DIR = DATA_DIR / "npcs"


def _ensure() -> None:
    NPC_DIR.mkdir(parents=True, exist_ok=True)


def save_npc(record: dict, trades: dict | None = None) -> dict:
    """Save an NPC record (and its trades, if given). Returns the record."""
    _ensure()
    npc_id = record["npc_id"]
    if trades is not None:
        trades_path = NPC_DIR / f"{npc_id}_trades.json"
        trades_path.write_text(json.dumps(trades))
        record["trades_path"] = str(trades_path)
    (NPC_DIR / f"{npc_id}.json").write_text(json.dumps(record, indent=2))
    return record


def list_npcs() -> list[dict]:
    _ensure()
    out = []
    for p in sorted(NPC_DIR.glob("*.json")):
        if p.name.endswith("_trades.json"):
            continue
        out.append(json.loads(p.read_text()))
    return out


def get_npc(npc_id: str) -> dict | None:
    p = NPC_DIR / f"{npc_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def get_trades(npc_id: str) -> dict | None:
    rec = get_npc(npc_id)
    if not rec or not rec.get("trades_path"):
        return None
    p = Path(rec["trades_path"])
    return json.loads(p.read_text()) if p.exists() else None


def find_by_url(url: str) -> dict | None:
    """Same-link matching: a plain lookup that must always work."""
    norm = normalize_url(url)
    for rec in list_npcs():
        for v in rec.get("source_videos", []):
            if normalize_url(v.get("url", "")) == norm:
                return rec
    return None


def normalize_url(url: str) -> str:
    """Reduce YouTube links to their video id so watch?v=, youtu.be and shorts match."""
    u = url.strip()
    for marker in ("v=", "youtu.be/", "shorts/"):
        if marker in u:
            return u.split(marker, 1)[1].split("&")[0].split("?")[0].split("/")[0]
    return u
