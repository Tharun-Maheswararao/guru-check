# API (shared)

FastAPI server (`server.py`) that also serves the frontend. See `frontend/README.md` to run it.

`POST /api/birth` runs `backend.pipeline.birth_npc(url, on_step)` in a thread and the UI polls
`GET /api/birth/{job}` for the steps. Talk (`talk.py`) uses Hydrogen with low thinking: Gemini 4
thinking counts toward `maxOutputTokens`, and a small budget returns an empty answer.
