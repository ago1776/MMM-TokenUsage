import json
import tempfile
import unittest
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("openclaw_collector", ROOT / "collectors" / "openclaw.py")
COLLECTOR = module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


def write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


class CollectorTest(unittest.TestCase):
    def test_cache_exclusion_deduplication_and_daily_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            openclaw = root / ".openclaw"
            claude = root / ".claude"

            claude_event = {
                "type": "assistant",
                "timestamp": "2026-01-01T23:30:00Z",  # 02.01. in Europe/Berlin
                "message": {"id": "claude-1", "usage": {"input_tokens": 11, "output_tokens": 7}},
            }
            write_jsonl(claude / "projects" / "project" / "one.jsonl", [claude_event])
            write_jsonl(claude / "projects" / "project" / "duplicate.jsonl", [claude_event])

            classic = {
                "timestamp": "2026-01-02T10:00:00Z",
                "message": {
                    "id": "wrapper-1", "model": "gpt-test",
                    "usage": {"input": 999, "output": 1, "cacheRead": 5000},
                },
            }
            session = openclaw / "agents" / "demo" / "sessions" / "session.jsonl"
            write_jsonl(session, [classic])
            write_jsonl(session.with_name("session.jsonl.reset.1"), [classic])

            rollout = openclaw / "agents" / "demo" / "agent" / "codex-home" / "sessions" / "2026" / "01" / "02" / "rollout-a.jsonl"
            write_jsonl(rollout, [
                {"type": "turn_context", "timestamp": "2026-01-02T10:00:00Z", "payload": {"model": "gpt-test"}},
                {"type": "event_msg", "timestamp": "2026-01-02T10:01:00Z", "payload": {
                    "type": "token_count", "info": {"last_token_usage": {
                        "input_tokens": 100, "cached_input_tokens": 80,
                        "output_tokens": 10, "reasoning_output_tokens": 4,
                    }}
                }},
            ])

            data = COLLECTOR.collect_data(
                2, date(2026, 1, 2), ZoneInfo("Europe/Berlin"), openclaw, claude
            )
            self.assertEqual(data["days"], ["01.01.", "02.01."])
            self.assertEqual(data["claude_daily"], [0, 18])
            self.assertEqual(data["openai_daily"], [0, 30])
            self.assertEqual(data["counting"]["cache"], "excluded")
            self.assertEqual(data["fallback_days"], [])

    def test_classic_wrapper_is_used_when_no_codex_rollout_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / ".openclaw" / "agents" / "demo" / "sessions" / "session.jsonl"
            write_jsonl(session, [{
                "timestamp": "2026-01-02T10:00:00Z",
                "message": {"id": "legacy", "model": "gpt-test", "usage": {"input": 12, "output": 8}},
            }])
            data = COLLECTOR.collect_data(
                1, date(2026, 1, 2), ZoneInfo("UTC"), root / ".openclaw", root / ".claude"
            )
            self.assertEqual(data["openai_daily"], [20])


if __name__ == "__main__":
    unittest.main()
