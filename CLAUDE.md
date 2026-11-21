# Guru Check: NPC Edition (Gemini 4 NYC Hackathon)

Team of 3. I am **Person 3**: web app, NPC library, voice chat, Simulate replay, portraits, demo.
Only edit `frontend/`, `backend/api/`, `backend/npc_store/` unless asked. Persons 1 and 2 own
watcher, scanner, extractor, matcher, backtester, randoms, skeptic, and will add `backend/pipeline.py`.

## Run
```bash
pip install -r requirements.txt
python3 frontend/mock_npcs.py              # fake NPCs, marked DEMO DATA
MOCK_BIRTH=1 uvicorn backend.api.server:app --reload --port 8000
```
Open http://localhost:8000 in Chrome (voice uses Web Speech API).

## Layout
- `frontend/index.html, style.css, app.js`: plain JS, no build step. Hash routes `#/`, `#/npc/<id>`, `#/sim/<id>`.
- `backend/api/server.py`: FastAPI. `/api/npcs`, `/api/npcs/{id}`, `/api/npcs/{id}/trades`, `/api/npcs/{id}/talk`, `/api/npcs/{id}/portrait`, `/api/birth`, `/api/birth/{job}`. Serves the frontend.
- `backend/api/talk.py`: Gemini Hydrogen chat grounded only in saved numbers (`GEMINI_TALK_MODEL` env). Template fallback without `GEMINI_API_KEY`.
- `backend/npc_store/store.py`: JSON per NPC in `data/npcs/` (gitignored). `save_npc(record, trades)`.
- Contracts: `schemas/npc_record.json`, `schemas/trades.json`. `frontend/README.md` lists the extra fields the UI reads.
- `frontend/DEMO.md`: 3 minute stage script.

## Rules
- Style: arcade at night. Colors ink #12101C, panel #1E1A2E, gold #FFC93C, green #3DDC84, red #FF5470, cyan #7FD8FF, muted #8F88AD. Fonts Press Start 2P (labels) and Space Grotesk (text). 4px #0B0913 borders, hard offset shadows.
- Every screen shows "Not financial advice, a test of what the video claims."
- NPCs are fictional characters, never the real creator. The NPC never invents numbers.
- Never download YouTube videos. No em dashes in any text.
- Deadline: integration 3:00 PM, submit 4:45 PM. Delete `data/npcs/demo-*` before judging.
