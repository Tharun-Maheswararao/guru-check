"""NPC voices from Gemini text to speech (gemini-3.8-flash-tts through the Interactions API).

Each NPC gets a voice from its color, so the same trader always sounds the same. Returns MP3
bytes. The UI falls back to the browser's speech if this fails, so the demo never goes silent.
"""

import base64
import time
from functools import lru_cache

from backend import llm
from backend.config import TTS

VOICES = {"gold": "Puck", "green": "Kore", "red": "Fenrir", "cyan": "Charon", "violet": "Aoede"}


def voice_for(record: dict) -> str:
    return VOICES.get(record.get("color", ""), "Kore")


@lru_cache(maxsize=256)
def _speak(text: str, voice: str | None) -> bytes:
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


def speak(text: str, record: dict) -> bytes:
    """MP3 of the NPC saying text. Falls back to the default voice if the NPC's voice is rejected."""
    text = " ".join(text.split())[:1000]
    try:
        return _speak(text, voice_for(record))
    except Exception:
        return _speak(text, None)
