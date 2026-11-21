"""Thin wrappers over the Gemini models Person 1 uses.

- hydrogen_json(): Gemini 4 Hydrogen through the Interactions API, returning parsed JSON
  (Watcher, Extractor). A YouTube link goes in as a video block; the video is never downloaded.
- hydrogen_text(): same, plain text (eval baseline).
- decide(): Gemini Decisions API, returning plain dicts (Scanner, Matcher, router, eval judge).

Every call is counted and logged to data/logs/llm_calls.jsonl (model, kind, prompt, output,
seconds), so we can debug prompts and keep request volume at normal hackathon levels.

Tests swap these out by passing fakes where a module takes `llm_json=` or `decide=`.
"""

import json
import logging
import re
import threading
import time
from collections import Counter
from functools import lru_cache
from typing import Any, Callable

from backend.config import DATA_DIR, DECISIONS, HYDROGEN, ModelSettings

log = logging.getLogger("guru_check.llm")
CALLS: Counter = Counter()  # requests sent this process, by kind
_log_lock = threading.Lock()


class MissingKeyError(RuntimeError):
    pass


@lru_cache(maxsize=None)
def _client(settings: ModelSettings):
    from google import genai

    if not settings.api_key:
        raise MissingKeyError(
            f"No API key for {settings.name}. Set GEMINI_API_KEY (or {settings.name}_API_KEY) in .env"
        )
    http_options: dict[str, Any] = {"api_version": "v1beta"}
    if settings.base_url:
        http_options["base_url"] = settings.base_url
    return genai.Client(api_key=settings.api_key, http_options=http_options)


def _record(kind: str, model: str, prompt: Any, output: Any, seconds: float) -> None:
    CALLS[kind] += 1
    log.info("%s %s %.1fs", kind, model, seconds)
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "model": model,
             "seconds": round(seconds, 2), "prompt": prompt, "output": output}
    try:
        path = DATA_DIR / "logs" / "llm_calls.jsonl"
        with _log_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def _retry(fn: Callable[[], Any], attempts: int = 5) -> Any:
    """Retry 429 and 5xx (new models often return 503 'overwhelmed'); fail fast on other 4xx."""
    for i in range(attempts):
        try:
            return fn()
        except MissingKeyError:
            raise
        except Exception as e:
            code = getattr(e, "code", None) or getattr(e, "status_code", None)
            if i == attempts - 1 or (isinstance(code, int) and 400 <= code < 500 and code != 429):
                if code == 429:
                    raise RuntimeError(
                        "429 from the Gemini API. If it keeps happening the project may have hit its "
                        "spend cap: raise it a little at https://aistudio.google.com/spend"
                    ) from e
                raise
            time.sleep(min(2 ** i, 20))


def parse_json(text: str) -> Any:
    """Parse model output that should be JSON, tolerating ``` fences or text around it."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _hydrogen_request(prompt: str, youtube_url: str | None, thinking_level: str,
                      schema: dict | None, settings: ModelSettings) -> dict:
    blocks: list[dict] = [{"type": "text", "text": prompt}]
    if youtube_url:
        blocks.append({"type": "video", "uri": youtube_url})
    request: dict[str, Any] = {
        "model": settings.model,
        "input": blocks,
        "generation_config": {"thinking_level": thinking_level},
        "store": False,  # don't keep conversation state on Google's side
    }
    if schema is not None:
        request["response_format"] = {"type": "text", "mime_type": "application/json", "schema": schema}
    return request


def _hydrogen(kind: str, prompt: str, youtube_url: str | None, thinking_level: str,
              schema: dict | None, settings: ModelSettings) -> str:
    request = _hydrogen_request(prompt, youtube_url, thinking_level, schema, settings)

    def call():
        start = time.time()
        interaction = _client(settings).interactions.create(**request)
        text = interaction.output_text or ""
        _record(kind, settings.model, {"text": prompt, "video": youtube_url}, text, time.time() - start)
        return text

    return _retry(call)


def hydrogen_json(prompt: str, youtube_url: str | None = None, schema: dict | None = None,
                  thinking_level: str = "medium", settings: ModelSettings = HYDROGEN) -> Any:
    """Ask Hydrogen for JSON, constrained by `schema` (a JSON Schema dict) when given."""
    if schema is None:
        prompt += "\n\nReturn only JSON."
    return parse_json(_hydrogen("hydrogen_json", prompt, youtube_url, thinking_level, schema, settings))


def hydrogen_text(prompt: str, youtube_url: str | None = None, thinking_level: str = "low",
                  settings: ModelSettings = HYDROGEN) -> str:
    return _hydrogen("hydrogen_text", prompt, youtube_url, thinking_level, None, settings)


def _answer_to_dict(answer: Any) -> dict:
    if hasattr(answer, "model_dump"):
        return answer.model_dump(exclude_none=True)
    return dict(answer)


def decide(input: str | list, questions: dict, settings: ModelSettings = DECISIONS) -> dict[str, dict]:
    """Ask several Decisions API questions about one input in one request.

    Returns {question_key: answer dict}. Answers carry `noul` (probability of yes) for yes/no
    questions, `choice` and `probabilities` for choice questions, `score` for score questions,
    and `confidence`. Up to 1,000 questions per request; the input is billed once.
    """
    if not 1 <= len(questions) <= 1000:
        raise ValueError(f"Decisions API takes 1 to 1000 questions, got {len(questions)}")

    def call():
        start = time.time()
        resp = _client(settings).decisions.create(model=settings.model, input=input, questions=questions)
        feedback = getattr(resp, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise RuntimeError(f"Decisions API blocked the input: {feedback.block_reason}")
        answers = {key: _answer_to_dict(ans) for key, ans in resp.answers.items()}
        _record("decide", settings.model, {"input": input, "questions": list(questions)}, answers,
                time.time() - start)
        return answers

    return _retry(call)


def yes_no(instructions: str, true_description: str = "", false_description: str = "") -> dict:
    """Build a Decisions API yes/no (noul) question."""
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true_description or false_description:
        q["criteria"] = {"true_description": true_description, "false_description": false_description}
    return q
