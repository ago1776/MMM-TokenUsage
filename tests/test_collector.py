import json
import tempfile
import unittest
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("collector", ROOT / "collectors" / "collect.py")
COLLECTOR = module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


def write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def series_by_id(data):
    return {item["id"]: item for item in data["series"]}


class CollectorTest(unittest.TestCase):
    def test_claude_code_and_codex_without_any_runtime_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            claude = root / ".claude"
            codex = root / ".codex"
            claude_event = {
                "type": "assistant",
                "timestamp": "2026-01-01T23:30:00Z",
                "message": {"id": "claude-1", "usage": {"input_tokens": 11, "output_tokens": 7}},
            }
            write_jsonl(claude / "projects" / "project" / "one.jsonl", [claude_event])
            write_jsonl(claude / "projects" / "project" / "duplicate.jsonl", [claude_event])
            rollout = codex / "sessions" / "2026" / "01" / "02" / "rollout-a.jsonl"
            write_jsonl(rollout, [
                {"type": "session_meta", "payload": {"model_provider": "openai"}},
                {"type": "event_msg", "timestamp": "2026-01-02T10:01:00Z", "payload": {
                    "type": "token_count", "info": {"last_token_usage": {
                        "input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 10,
                    }}
                }},
            ])

            data = COLLECTOR.build_data(
                2, date(2026, 1, 2), ZoneInfo("Europe/Berlin"),
                [claude], [codex], [], [],
            )

            providers = series_by_id(data)
            self.assertEqual(data["schema_version"], 2)
            self.assertEqual(data["dates"], ["2026-01-01", "2026-01-02"])
            self.assertEqual(providers["claude"]["daily"], [0, 18])
            self.assertEqual(providers["openai"]["daily"], [0, 30])

    def test_arbitrary_provider_json_is_merged(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "usage.json"
            source.write_text(json.dumps({
                "schema_version": 2,
                "generated": "2026-01-02T12:00:00Z",
                "dates": ["2026-01-01", "2026-01-02"],
                "series": [{
                    "id": "gemini", "label": "Gemini", "color": "#123456", "daily": [12, 34]
                }],
            }), encoding="utf-8")

            data = COLLECTOR.build_data(
                2, date(2026, 1, 2), ZoneInfo("UTC"), [], [], [str(source)], []
            )

            gemini = series_by_id(data)["gemini"]
            self.assertEqual(gemini["daily"], [12, 34])
            self.assertEqual(gemini["color"], "#123456")

    def test_simple_csv_supports_multiple_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "usage.csv"
            source.write_text(
                "date,provider,tokens,label,color\n"
                "2026-01-01,openrouter,15,OpenRouter,#7654ff\n"
                "2026-01-02,mistral,20,Mistral,#ff9900\n"
                "2026-01-02,openrouter,5,OpenRouter,#7654ff\n",
                encoding="utf-8",
            )

            data = COLLECTOR.build_data(
                2, date(2026, 1, 2), ZoneInfo("UTC"), [], [], [], [str(source)]
            )

            providers = series_by_id(data)
            self.assertEqual(providers["openrouter"]["daily"], [15, 5])
            self.assertEqual(providers["mistral"]["daily"], [0, 20])

    def test_legacy_v1_json_can_be_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "legacy.json"
            source.write_text(json.dumps({
                "generated": "2026-01-02 07:00",
                "claude_daily": [10, 20],
                "openai_daily": [0, 5],
            }), encoding="utf-8")

            data = COLLECTOR.build_data(
                2, date(2026, 1, 2), ZoneInfo("UTC"), [], [], [str(source)], []
            )

            providers = series_by_id(data)
            self.assertEqual(providers["claude"]["daily"], [10, 20])
            self.assertEqual(providers["openai"]["daily"], [0, 5])


if __name__ == "__main__":
    unittest.main()
