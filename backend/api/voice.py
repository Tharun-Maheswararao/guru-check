"""NPC voices from Gemini text to speech (gemini-3.8-flash-lite-tts by default, through the Interactions API).

Each NPC gets a voice from its color, so the same trader always sounds the same. Returns MP3
bytes. The UI falls back to the browser's speech if this fails, so the demo never goes silent.

To cut the wait between text and voice, /talk calls prefetch() as soon as the answer exists: the
answer is split into its first sentence and the rest, both are synthesized in the background, and
/speak hands over each one as soon as it is ready. The UI shows the text when the voice starts.
"""

import base64
import time
import re
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor

from backend import llm
from backend.config import TTS

VOICES = {"gold": "Puck", "green": "Kore", "red": "Fenrir", "cyan": "Charon", "violet": "Aoede"}


def voice_for(record: dict) -> str:
    return VOICES.get(record.get("color", ""), "Kore")


_POOL = ThreadPoolExecutor(max_workers=6)
_JOBS: "OrderedDict[tuple[str, str | None], Future]" = OrderedDict()
_LOCK = threading.Lock()


def _synth(text: str, voice: str | None) -> bytes:
    start = time.time()
    config = {"speech_config": [{"voice": voice}]} if voice else {}
    interaction = llm._client(TTS).interactions.create(
        model=TTS.model, store=False, response_modalities=["audio"],
        response_format={"type": "audio", "mime_type": "audio/mp3"}, generation_config=config,
        input=[{"type": "text", "text": text}],
    )
    audio = interaction.output_audio
    if audio is None or not audio.data:
        raise RuntimeError("Speech model returned no audio")
    data = base64.b64decode(audio.data) if isinstance(audio.data, str) else audio.data
    llm._record("voice", TTS.model, text, f"{len(data)} bytes, voice {voice}", time.time() - start)
    return data


def _job(text: str, voice: str | None) -> Future:
    """One background synthesis per (text, voice), shared by prefetch and /speak, kept for reuse."""
    key = (text, voice)
    with _LOCK:
        job = _JOBS.get(key)
        if job is None or (job.done() and job.exception() is not None):
            job = _POOL.submit(_synth, text, voice)
            _JOBS[key] = job
            while len(_JOBS) > 256:
                _JOBS.popitem(last=False)
        return job


def _clean(text: str) -> str:
    return " ".join(text.split())[:1000]


def split_chunks(text: str) -> list[str]:
    """The first sentence on its own, then the rest. A short first chunk comes back from the voice
    model sooner, so the NPC starts talking while the rest is still being made."""
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", _clean(text)) if x]
    if len(sentences) <= 1:
        return sentences
    first, rest = sentences[0], sentences[1:]
    while len(first) < 40 and rest:  # don't make a chunk out of "Easy there."
        first = f"{first} {rest.pop(0)}"
    return [first] + ([" ".join(rest)] if rest else [])


def prefetch(text: str, record: dict) -> list[str]:
    """Start synthesizing an answer right away. Returns the chunks the UI should ask for, in order."""
    chunks = split_chunks(text)
    for chunk in chunks:
        _job(chunk, voice_for(record))
    return chunks


def speak(text: str, record: dict) -> bytes:
    """MP3 of the NPC saying text. Falls back to the default voice if the NPC's voice is rejected."""
    text = _clean(text)
    try:
        return _job(text, voice_for(record)).result(timeout=40)
    except Exception:
        return _job(text, None).result(timeout=40)
