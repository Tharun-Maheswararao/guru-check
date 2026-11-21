"""Watcher: YouTube link -> timestamped segments of speech and on-screen details.

Hydrogen reads the link directly through the Gemini API. The video is never downloaded.
Output format is documented in backend/watcher/README.md.
"""

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Callable

from backend import llm

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

PROMPT = """You are watching a trading strategy video. Split the whole video, start to end, into
consecutive segments of roughly 10 to 30 seconds, breaking at natural pauses or topic changes.

For each segment return:
- start_s, end_s: start and end time in seconds from the video start, as numbers.
- speech: what is said in that span, close to word for word, in English (translate if needed).
  Use an empty string if nobody speaks.
- on_screen: what is visible that matters for the strategy: chart symbol and timeframe, indicators
  with their exact settings (e.g. "EMA 50 and EMA 200", "RSI 14 with 30/70 lines"), drawings such as
  zones, trendlines, entry/stop/target markers, and any text overlays with numbers or rules.
  Use an empty string if nothing relevant is shown.

Also return the language spoken and whether the video has background music over speech.

Return only JSON in exactly this shape:
{"language": "en", "music_over_speech": false,
 "segments": [{"start_s": 0, "end_s": 12.5, "speech": "...", "on_screen": "..."}]}"""


SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "music_over_speech": {"type": "boolean"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_s": {"type": "number"},
                    "end_s": {"type": "number"},
                    "speech": {"type": "string"},
                    "on_screen": {"type": "string"},
                },
                "required": ["start_s", "end_s", "speech", "on_screen"],
            },
        },
    },
    "required": ["language", "music_over_speech", "segments"],
}


def video_id(url: str) -> str:
    """Extract the 11 character YouTube id from any common link form."""
    url = url.strip()
    if _ID_RE.match(url):
        return url
    parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        query = urllib.parse.parse_qs(parsed.query)
        if "v" in query:
            candidate = query["v"][0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            candidate = parts[1] if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v") else ""
    else:
        candidate = ""
    if not _ID_RE.match(candidate):
        raise ValueError(f"Not a YouTube video link: {url}")
    return candidate


def canonical_url(url: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id(url)}"


def fetch_title(url: str) -> str:
    """Video title from YouTube's public oEmbed endpoint. Returns "" if unavailable."""
    endpoint = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "guru-check"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp).get("title", "")
    except Exception:
        return ""


def parse_time(value: Any) -> float:
    """Accept seconds as a number or string, or "MM:SS" / "HH:MM:SS"."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("s")
    if ":" in text:
        seconds = 0.0
        for part in text.split(":"):
            seconds = seconds * 60 + float(part)
        return seconds
    return float(text)


def clean_segments(raw: list[dict]) -> list[dict]:
    """Normalize times, drop empty segments, sort, and number them from 0."""
    segments = []
    for seg in raw:
        try:
            start = parse_time(seg.get("start_s", seg.get("start", 0)))
            end = parse_time(seg.get("end_s", seg.get("end", start)))
        except (TypeError, ValueError):
            continue
        speech = str(seg.get("speech") or "").strip()
        on_screen = str(seg.get("on_screen") or "").strip()
        if not speech and not on_screen:
            continue
        segments.append({"start_s": round(start, 1), "end_s": round(max(end, start), 1),
                         "speech": speech, "on_screen": on_screen})
    segments.sort(key=lambda s: s["start_s"])
    return [{"segment_id": i, **seg} for i, seg in enumerate(segments)]


def watch(url: str, llm_json: Callable[..., Any] = llm.hydrogen_json, title: str | None = None) -> dict:
    """Run the Watcher on one YouTube link."""
    url = canonical_url(url)
    raw = llm_json(PROMPT, youtube_url=url, schema=SCHEMA)
    if isinstance(raw, list):
        raw = {"segments": raw}
    segments = clean_segments(raw.get("segments", []))
    if not segments:
        raise RuntimeError(f"Watcher returned no segments for {url}")
    return {
        "video": {
            "url": url,
            "video_id": video_id(url),
            "title": fetch_title(url) if title is None else title,
            "upload_date": "",
            "duration_s": segments[-1]["end_s"],
            "language": raw.get("language", ""),
            "music_over_speech": bool(raw.get("music_over_speech", False)),
        },
        "segments": segments,
    }
