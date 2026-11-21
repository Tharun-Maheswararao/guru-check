"""Backend API plus the frontend, on one port.

    pip install fastapi uvicorn
    python3 scripts/seed_demo.py          # optional demo NPCs
    uvicorn backend.api.server:app --reload --port 8000
    open http://localhost:8000
"""

import json
import os
import random
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.api.portrait import generate_portrait
from backend.api.talk import talk as talk_to_npc
from backend.api.voice import speak
from backend.npc_store import store

ROOT = Path(__file__).resolve().parents[2]
app = FastAPI(title="Guru Check")
JOBS: dict[str, dict] = {}


class BirthIn(BaseModel):
    url: str


class TalkIn(BaseModel):
    question: str
    history: list[dict] = []


def _card(rec: dict) -> dict:
    r = rec.get("results") or {}
    return {k: rec.get(k) for k in ("npc_id", "name", "color", "archetype", "verdict", "portrait_path", "demo")} | {
        "return_pct": round(100 * (r["final_balance"] / 10000 - 1), 1) if r.get("final_balance") else None,
        "video_title": (rec.get("source_videos") or [{}])[0].get("title"),
    }


@app.get("/api/npcs")
def list_npcs():
    return [_card(r) for r in store.list_npcs()]


@app.get("/api/npcs/{npc_id}")
def get_npc(npc_id: str):
    rec = store.get_npc(npc_id)
    if not rec:
        raise HTTPException(404, "No such NPC")
    return rec


@app.get("/api/npcs/{npc_id}/trades")
def get_trades(npc_id: str):
    t = store.get_trades(npc_id)
    if not t:
        raise HTTPException(404, "No trades for this NPC")
    return t


@app.post("/api/npcs/{npc_id}/talk")
def talk(npc_id: str, body: TalkIn):
    rec = store.get_npc(npc_id)
    if not rec:
        raise HTTPException(404, "No such NPC")
    return talk_to_npc(rec, store.get_trades(npc_id), body.question, body.history)


@app.post("/api/birth")
def birth(body: BirthIn):
    existing = store.find_by_url(body.url)
    if existing:  # same-link matching, always works
        return {"status": "exists", "npc_id": existing["npc_id"]}
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "running", "steps": [], "npc_id": None, "error": None, "preview": None}

    def on_step(step, detail=""):
        JOBS[job_id]["steps"].append({"step": step, "detail": detail, "t": time.time()})

    def run():
        # Persons 1 and 2 provide backend/pipeline.py with birth_npc(url, on_step) -> npc record.
        # on_step(step, detail) with step in: watch, scan, extract, match, backtest, randoms, judge, born.
        try:
            from backend.pipeline import birth_npc
        except ImportError:
            birth_npc = None
        if os.environ.get("MOCK_BIRTH") or birth_npc is None:
            if not os.environ.get("MOCK_BIRTH"):
                JOBS[job_id].update(status="error", error="Pipeline not connected yet. Set MOCK_BIRTH=1 to rehearse.")
                return
            mock_birth(body.url, on_step, job_id)
            return
        try:
            rec = birth_npc(body.url, on_step, on_rules=lambda p: JOBS[job_id].update(preview=p),
                            make_portrait=None if os.environ.get("PORTRAITS") == "0" else generate_portrait)
            JOBS[job_id].update(status="done", npc_id=rec["npc_id"])
        except Exception as e:
            JOBS[job_id].update(status="error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=run, daemon=True).start()
    return {"status": "running", "job_id": job_id}


MOCK_STEPS = [
    ("watch", "Hydrogen is watching the video"),
    ("scan", "Decisions API is scoring 48 segments"),
    ("extract", "Hydrogen is writing the exact rules"),
    ("match", "Checking the library for the same strategy"),
    ("backtest", "Neon agent is backtesting every meaning of the rules"),
    ("randoms", "Racing 1,000 random traders"),
    ("judge", "Carbon is judging the claims"),
]


def mock_birth(url, on_step, job_id):
    """UI rehearsal only (MOCK_BIRTH=1): replays the steps, then clones a demo NPC for this link."""
    demos = [r for r in store.list_npcs() if r.get("demo") and r.get("results")]
    if not demos:
        JOBS[job_id].update(status="error", error="Run scripts/seed_demo.py first")
        return
    for step, detail in MOCK_STEPS:
        on_step(step, detail)
        time.sleep(1.2)
    src = random.choice(demos)
    rec = json.loads(json.dumps(src))
    rec["npc_id"] = "demo-mock-" + uuid.uuid4().hex[:6]
    rec["source_videos"] = [{**src["source_videos"][0], "url": url}]
    trades = store.get_trades(src["npc_id"])
    store.save_npc(rec, trades)
    on_step("born", f"{rec['name']} is born")
    JOBS[job_id].update(status="done", npc_id=rec["npc_id"])


class SpeakIn(BaseModel):
    text: str


@app.post("/api/npcs/{npc_id}/speak")
def npc_speak(npc_id: str, body: SpeakIn):
    """MP3 of the NPC saying text, in its own Gemini voice. 503 tells the UI to use browser speech."""
    rec = store.get_npc(npc_id)
    if not rec:
        raise HTTPException(404, "No such NPC")
    if not os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_VOICE") == "0":
        raise HTTPException(503, "Gemini voice is off")
    try:
        return Response(content=speak(body.text, rec), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(503, f"Gemini voice failed: {type(e).__name__}")


@app.get("/api/npcs/{npc_id}/portrait")
def portrait(npc_id: str):
    rec = store.get_npc(npc_id)
    p = Path(rec.get("portrait_path") or "") if rec else None
    if not p or not p.is_file():
        raise HTTPException(404, "No portrait")
    return FileResponse(p)


@app.get("/api/birth/{job_id}")
def birth_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "No such job")
    return JOBS[job_id]


app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")
