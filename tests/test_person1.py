"""Offline tests for Watcher, Scanner, Extractor, Matcher, pipeline and eval, with fake model calls.

    python -m unittest discover tests
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from backend.extractor import rules as R
from backend.extractor.extractor import build_record, extract
from backend.matcher.matcher import match, match_link
from backend.npc_store.store import Store
from backend.pipeline import run
from backend.scanner import router
from backend.scanner.scanner import LABELS, flagged_segments, scan
from backend.watcher.watcher import clean_segments, parse_time, video_id, watch
from eval.run_eval import evaluate

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
URL2 = "https://youtu.be/9bZkp7q19f0"

WATCH_RAW = {
    "language": "en",
    "segments": [
        {"start_s": "0:00", "end_s": "0:20", "speech": "This strategy has an 80 percent win rate.", "on_screen": ""},
        {"start_s": 20, "end_s": 45, "speech": "Use the daily chart on Bitcoin.", "on_screen": "BTCUSD 1D, EMA 50, EMA 200"},
        {"start_s": 45, "end_s": 70, "speech": "Buy when the 50 EMA crosses above the 200 EMA.", "on_screen": ""},
        {"start_s": 70, "end_s": 90, "speech": "Sell when it crosses back below. Stop below the swing low.", "on_screen": ""},
        {"start_s": 90, "end_s": 100, "speech": "", "on_screen": ""},
        {"start_s": 100, "end_s": 120, "speech": "Like and subscribe!", "on_screen": ""},
    ],
}

EXTRACT_RAW = {
    "market_stated": "Bitcoin", "timeframe_stated": "daily",
    "entry": [{"rule": "50 EMA crosses above 200 EMA", "timestamp_s": 50}],
    "exit": [{"rule": "50 EMA crosses below 200 EMA", "timestamp_s": 72}],
    "stop_loss": [{"rule": "just below the most recent swing low", "timestamp_s": 999}],
    "filters": [],
    "vague_terms": [{"term": "swing low", "meanings": ["lowest low of last 5 bars", "lowest low of last 10 bars"]},
                    {"term": "only one", "meanings": ["x"]}],
    "claims": [{"text": "80 percent win rate", "timestamp_s": 3}],
    "testable": True, "untestable_reason": None,
}

KEYWORDS = {"entry": "buy when", "exit": "sell when", "stop_loss": "stop below", "filter": "only trade",
            "setup": "daily chart", "claim": "win rate"}


def _block(text, header, next_header):
    match = re.search(rf"{re.escape(header)}(.*?)(?={re.escape(next_header)}|\Z)", text, re.S)
    return match.group(1) if match else ""


def fake_decide(text, questions):
    """Keyword-based stand-in for the Decisions API, understanding the batched question keys."""
    out = {}
    for key, q in questions.items():
        if q["type"] == "choice":
            out[key] = {"type": "choice", "choice": "performance" if "worst" in text else "other",
                        "probabilities": {}, "confidence": 0.9}
        elif "__" in key:  # Scanner: s<segment_id>__<label>
            sid, label = key[1:].split("__")
            seg = _block(text, f"Segment S{sid} ", "\n\nSegment S").lower()
            out[key] = {"type": "noul", "noul": 0.95 if KEYWORDS[label] in seg else 0.02, "confidence": 0.9}
        elif key.startswith("same_c"):  # Matcher: same_c<n>
            new = text.split("Candidate C")[0]
            cand = _block(text, f"Candidate C{key[6:]}:", "\n\nCandidate C")
            out[key] = {"type": "noul", "noul": 0.97 if "EMA" in new and "EMA" in cand else 0.05, "confidence": 0.9}
        else:  # eval judge: r<n>
            out[key] = {"type": "noul", "noul": 0.9, "confidence": 0.9}
    return out


class CountingDecide:
    def __init__(self):
        self.requests = []

    def __call__(self, text, questions):
        self.requests.append(len(questions))
        return fake_decide(text, questions)


def fake_llm(prompt, youtube_url=None, **_):
    if youtube_url:
        return json.loads(json.dumps(WATCH_RAW))
    return json.loads(json.dumps(EXTRACT_RAW))


class WatcherTests(unittest.TestCase):
    def test_video_id_forms(self):
        for url in [URL, "youtube.com/watch?v=dQw4w9WgXcQ&t=30", "https://youtu.be/dQw4w9WgXcQ?si=x",
                    "https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
                    "dQw4w9WgXcQ"]:
            self.assertEqual(video_id(url), "dQw4w9WgXcQ", url)
        with self.assertRaises(ValueError):
            video_id("https://vimeo.com/123")

    def test_parse_time(self):
        self.assertEqual(parse_time("4:12"), 252)
        self.assertEqual(parse_time("1:00:05"), 3605)
        self.assertEqual(parse_time("12.5s"), 12.5)
        self.assertEqual(parse_time(7), 7.0)

    def test_clean_segments_drops_empty_and_numbers(self):
        segs = clean_segments(WATCH_RAW["segments"])
        self.assertEqual(len(segs), 5)
        self.assertEqual([s["segment_id"] for s in segs], list(range(5)))
        self.assertEqual(list(segs[0]), ["segment_id", "start_s", "end_s", "speech", "on_screen"])

    def test_watch_output(self):
        out = watch(URL, llm_json=fake_llm, title="Test")
        self.assertEqual(out["video"]["video_id"], "dQw4w9WgXcQ")
        self.assertEqual(out["video"]["duration_s"], 120)


class ScannerTests(unittest.TestCase):
    def test_flags_and_timeline(self):
        out = scan(watch(URL, llm_json=fake_llm, title=""), decide=fake_decide)
        labels = {s["segment_id"]: s["labels"] for s in out["segments"]}
        self.assertEqual(labels[0], ["claim"])
        self.assertEqual(labels[1], ["setup"])
        self.assertEqual(labels[2], ["entry"])
        self.assertEqual(set(labels[3]), {"exit", "stop_loss"})
        self.assertEqual(labels[4], [])
        self.assertEqual(len(flagged_segments(out)), 4)
        self.assertEqual(set(out["segments"][0]["flags"]), set(LABELS))

    def test_scanner_batches_segments(self):
        many = {"video": {"url": URL}, "segments": [
            {"segment_id": i, "start_s": i * 10, "end_s": i * 10 + 10, "speech": "buy when x", "on_screen": ""}
            for i in range(23)]}
        counter = CountingDecide()
        out = scan(many, decide=counter)
        self.assertEqual(sorted(counter.requests), [18, 60, 60])  # 3 requests for 23 segments, not 23
        self.assertTrue(all(s["labels"] == ["entry"] for s in out["segments"]))

    def test_router(self):
        self.assertEqual(router.route("What was your worst year?", decide=fake_decide)["route"], "performance")


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.scanned = scan(watch(URL, llm_json=fake_llm, title="T"), decide=fake_decide)

    def test_record_is_valid_and_normalized(self):
        rec = extract(self.scanned, llm_json=fake_llm)
        self.assertEqual(R.validate(rec), [])
        self.assertEqual(rec["market"], {"stated": "Bitcoin", "tested_on": "BTC-USD"})
        self.assertEqual(rec["timeframe"], "1d")
        self.assertEqual(rec["entry"][0]["timestamp_s"], 50)  # inside a flagged segment: kept
        self.assertEqual(rec["stop_loss"][0]["timestamp_s"], 70)  # outside: snapped to nearest flagged start
        self.assertEqual([v["term"] for v in rec["vague_terms"]], ["swing low"])  # one-meaning term dropped

    def test_no_entry_is_untestable(self):
        rec = build_record({**EXTRACT_RAW, "entry": []}, self.scanned["video"], [(0, 100)])
        self.assertFalse(rec["testable"])
        self.assertIn("entry", rec["untestable_reason"])
        self.assertEqual(R.validate(rec), [])

    def test_nothing_flagged_is_untestable(self):
        empty = {**self.scanned, "segments": [{**s, "labels": []} for s in self.scanned["segments"]]}
        rec = extract(empty, llm_json=lambda *a, **k: self.fail("should not call the model"))
        self.assertFalse(rec["testable"])
        self.assertEqual(R.validate(rec), [])

    def test_strategy_id_ignores_order_case_and_sources(self):
        a = extract(self.scanned, llm_json=fake_llm)
        b = json.loads(json.dumps(a))
        b["entry"] = [{"rule": "50 EMA CROSSES   above 200 EMA.", "timestamp_s": 1}]
        b["source_videos"] = [{"url": URL2, "title": "", "upload_date": ""}]
        self.assertEqual(R.strategy_id(a), R.strategy_id(b))

    def test_schema_example_passes_validation(self):
        example = json.loads((ROOT / "schemas" / "strategy_rules.json").read_text())
        example["strategy_id"] = R.strategy_id(example)
        self.assertEqual(R.validate(example), [])


class MatcherAndPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pipeline_new_then_same_link_then_duplicate_video(self):
        first = run(URL, data_dir=self.data, llm_json=fake_llm, decide=fake_decide, log=lambda _: None)
        self.assertEqual(first["match"]["action"], "new")
        sid = first["match"]["strategy_id"]
        self.assertTrue((self.data / "strategies" / f"{sid}.json").exists())
        for stage in ["watch", "scan", "rules", "match"]:
            self.assertTrue((self.data / "runs" / "dQw4w9WgXcQ" / f"{stage}.json").exists())

        again = run(URL, data_dir=self.data, llm_json=lambda *a, **k: self.fail("no model calls"),
                    decide=lambda *a: self.fail("no model calls"), log=lambda _: None)
        self.assertEqual(again["match"]["action"], "open")

        # A second video teaching the same EMA cross, worded differently.
        def llm2(prompt, youtube_url=None, **_):
            out = fake_llm(prompt, youtube_url)
            if not youtube_url:
                out["entry"] = [{"rule": "Go long on the golden cross of the 50 and 200 EMA", "timestamp_s": 50}]
            return out

        second = run(URL2, data_dir=self.data, llm_json=llm2, decide=fake_decide, log=lambda _: None)
        self.assertEqual(second["match"]["action"], "join")
        self.assertEqual(second["match"]["strategy_id"], sid)
        saved = json.loads((self.data / "strategies" / f"{sid}.json").read_text())
        self.assertEqual(len(saved["source_videos"]), 2)

    def test_rerun_match_stage_does_not_match_itself(self):
        run(URL, data_dir=self.data, llm_json=fake_llm, decide=fake_decide, log=lambda _: None)
        rerun = run(URL, data_dir=self.data, redo_from="match", llm_json=fake_llm, decide=fake_decide,
                    log=lambda _: None)
        self.assertEqual(rerun["match"]["action"], "new")

    def test_reextracting_a_video_replaces_its_old_strategy(self):
        first = run(URL, data_dir=self.data, llm_json=fake_llm, decide=fake_decide, log=lambda _: None)

        def reworded(prompt, youtube_url=None, **_):
            out = fake_llm(prompt, youtube_url)
            if not youtube_url:
                out["entry"] = [{"rule": "Buy on the 50/200 EMA bullish crossover", "timestamp_s": 50}]
            return out

        second = run(URL, data_dir=self.data, redo_from="rules", llm_json=reworded, decide=fake_decide,
                     log=lambda _: None)
        self.assertNotEqual(first["match"]["strategy_id"], second["match"]["strategy_id"])
        saved = [p.stem for p in (self.data / "strategies").glob("*.json")]
        self.assertEqual(saved, [second["match"]["strategy_id"]])

    def test_below_threshold_is_new(self):
        store = Store(self.data)
        rec = run(URL, data_dir=self.data, llm_json=fake_llm, decide=fake_decide, log=lambda _: None)["rules"]
        other = json.loads(json.dumps(rec))
        other["entry"] = [{"rule": "RSI(14) crosses above 30", "timestamp_s": 50}]
        other["source_videos"] = [{"url": URL2, "title": "", "upload_date": ""}]
        other["strategy_id"] = R.strategy_id(other)
        never_same = lambda text, q: {k: {"noul": 0.4} for k in q}
        self.assertEqual(match(other, store, decide=never_same)["action"], "new")

    def test_matcher_uses_one_request_for_all_candidates(self):
        store = Store(self.data)
        rec = run(URL, data_dir=self.data, llm_json=fake_llm, decide=fake_decide, log=lambda _: None)["rules"]
        for i, url in enumerate(["https://youtu.be/aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb"]):
            other = json.loads(json.dumps(rec))
            other["entry"] = [{"rule": f"RSI(14) crosses above {30 + i}", "timestamp_s": 50}]
            other["source_videos"] = [{"url": url, "title": "", "upload_date": ""}]
            other["strategy_id"] = R.strategy_id(other)
            store.save_strategy(other)
        new = json.loads(json.dumps(rec))
        new["entry"] = [{"rule": "MACD crosses above signal", "timestamp_s": 50}]
        new["source_videos"] = [{"url": URL2, "title": "", "upload_date": ""}]
        new["strategy_id"] = R.strategy_id(new)
        counter = CountingDecide()
        decision = match(new, store, decide=counter)
        self.assertEqual(counter.requests, [3])
        self.assertEqual(len(decision["candidates"]), 3)

    def test_same_link_finds_born_npc(self):
        store = Store(self.data)
        store.save_npc({"npc_id": "npc1", "strategy_id": "abc", "source_videos": [{"url": "https://youtu.be/dQw4w9WgXcQ"}]})
        self.assertEqual(match_link(URL, store)["npc_id"], "npc1")


class EvalTests(unittest.TestCase):
    def test_metrics_on_fake_run(self):
        videos = [
            {"video_id": "a", "url": URL, "expected_testable": "true", "duplicate_group": "ema"},
            {"video_id": "b", "url": URL2, "expected_testable": "true", "duplicate_group": "ema"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            report = evaluate(videos, Path(tmp), baseline=True, decide=fake_decide, llm_json=fake_llm,
                              llm_text=lambda *a, **k: "It returned 340% since 2018.")
        m = report["metrics"]
        self.assertEqual(m["pipeline_errors"]["num"], 0)
        self.assertEqual(m["duplicates_matched"]["value"], 1.0)
        self.assertEqual(m["false_refusals"]["value"], 0.0)
        self.assertEqual(m["baseline_states_numbers"]["value"], 1.0)


if __name__ == "__main__":
    unittest.main()
