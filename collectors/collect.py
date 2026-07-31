#!/usr/bin/env python3
"""Collect daily token usage for MMM-TokenUsage from local clients or neutral feeds.

Built-in local adapters support Claude Code and Codex. Additional providers can be
merged from the public schema-v2 JSON format or a simple CSV file/URL. The collector
uses only Python's standard library and never reads credentials.
"""

from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import re
import sys
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PALETTE = ["#c96f4a", "#5aa6d8", "#8abf69", "#b58ad8", "#e0a84f", "#62b8a7"]
MAX_REMOTE_BYTES = 2 * 1024 * 1024


def parse_timestamp(timestamp: str | None, timezone: ZoneInfo | None) -> date | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return parsed.astimezone(timezone).date() if timezone else parsed.astimezone().date()
    except (ValueError, TypeError):
        return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def read_jsonl(path: str):
    try:
        handle = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return
    with handle:
        for line in handle:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def collect_claude_code(homes: list[Path], first: date, cutoff: float, timezone):
    daily = defaultdict(int)
    seen = set()
    for home in homes:
        for path in glob.glob(str(home / "projects" / "*" / "*.jsonl")):
            try:
                if os.path.getmtime(path) < cutoff:
                    continue
            except OSError:
                continue
            for event in read_jsonl(path):
                if event.get("type") != "assistant":
                    continue
                day = parse_timestamp(event.get("timestamp"), timezone)
                if day is None or day < first:
                    continue
                message = event.get("message") or {}
                usage = message.get("usage") or {}
                message_id = message.get("id") or event.get("requestId") or event.get("uuid")
                key = message_id or (
                    event.get("timestamp"), usage.get("input_tokens"), usage.get("output_tokens")
                )
                if key in seen:
                    continue
                seen.add(key)
                daily[day] += (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
    return daily


def collect_codex(homes: list[Path], first: date, cutoff: float, timezone):
    daily = defaultdict(int)
    seen_files = set()
    for home in homes:
        for path in glob.glob(str(home / "sessions" / "**" / "rollout-*.jsonl"), recursive=True):
            resolved = os.path.realpath(path)
            if resolved in seen_files:
                continue
            seen_files.add(resolved)
            try:
                if os.path.getmtime(path) < cutoff:
                    continue
            except OSError:
                continue
            current_model = ""
            model_provider = ""
            for event in read_jsonl(path):
                if event.get("type") == "session_meta":
                    model_provider = (event.get("payload") or {}).get("model_provider") or model_provider
                    continue
                if event.get("type") == "turn_context":
                    current_model = (event.get("payload") or {}).get("model") or current_model
                    continue
                payload = event.get("payload") or {}
                if (
                    event.get("type") != "event_msg"
                    or payload.get("type") != "token_count"
                    or (model_provider != "openai" and not current_model.startswith("gpt"))
                ):
                    continue
                day = parse_timestamp(event.get("timestamp"), timezone)
                if day is None or day < first:
                    continue
                usage = ((payload.get("info") or {}).get("last_token_usage") or {})
                if not usage:
                    continue
                gross_input = usage.get("input_tokens") or 0
                cached_input = usage.get("cached_input_tokens") or 0
                output = usage.get("output_tokens") or 0
                daily[day] += max(0, gross_input - cached_input) + output
    return daily


def read_source(source: str) -> str:
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": "MMM-TokenUsage/1.2"})
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(MAX_REMOTE_BYTES + 1)
        if len(raw) > MAX_REMOTE_BYTES:
            raise ValueError(f"source exceeds {MAX_REMOTE_BYTES} bytes: {source}")
        return raw.decode("utf-8")
    return Path(source).expanduser().read_text(encoding="utf-8")


def add_value(values, metadata, provider_id, label, color, day, tokens):
    provider_id = re.sub(r"[^a-z0-9._-]+", "-", str(provider_id).strip().lower()).strip("-")
    if not provider_id or day is None:
        return
    try:
        amount = max(0, int(tokens))
    except (TypeError, ValueError):
        return
    values[provider_id][day] += amount
    current = metadata.setdefault(provider_id, {})
    if label:
        current["label"] = str(label)
    if color:
        current["color"] = str(color)


def merge_json_source(source: str, values, metadata):
    data = json.loads(read_source(source))
    if isinstance(data.get("series"), list):
        dates = [parse_date(value) for value in data.get("dates", [])]
        if not dates:
            longest = max((len(item.get("daily", [])) for item in data["series"]), default=0)
            anchor = parse_date(data.get("generated"))
            if anchor and longest:
                dates = [anchor - timedelta(days=longest - 1 - index) for index in range(longest)]
        for item in data["series"]:
            for day, tokens in zip(dates, item.get("daily", [])):
                add_value(
                    values, metadata, item.get("id"), item.get("label"), item.get("color"), day, tokens
                )
        return

    # Schema v1 compatibility.
    arrays = [("claude", "Claude", data.get("claude_daily")),
              ("openai", "OpenAI", data.get("openai_daily"))]
    longest = max((len(array) for _, _, array in arrays if isinstance(array, list)), default=0)
    anchor = parse_date(data.get("generated"))
    dates = [anchor - timedelta(days=longest - 1 - index) for index in range(longest)] if anchor else []
    for provider_id, label, array in arrays:
        if not isinstance(array, list):
            continue
        for day, tokens in zip(dates[-len(array):], array):
            add_value(values, metadata, provider_id, label, None, day, tokens)


def merge_csv_source(source: str, values, metadata):
    reader = csv.DictReader(io.StringIO(read_source(source)))
    required = {"date", "provider", "tokens"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError(f"CSV requires columns date,provider,tokens: {source}")
    for row in reader:
        add_value(
            values, metadata, row.get("provider"), row.get("label"), row.get("color"),
            parse_date(row.get("date")), row.get("tokens"),
        )


def build_data(days, today, timezone, claude_homes, codex_homes, json_sources, csv_sources):
    first = today - timedelta(days=days - 1)
    local_tz = timezone or datetime.now().astimezone().tzinfo
    cutoff = datetime.combine(first, dt_time.min, tzinfo=local_tz).timestamp()
    values = defaultdict(lambda: defaultdict(int))
    metadata = {}

    if claude_homes:
        metadata["claude"] = {"label": "Claude", "color": PALETTE[0]}
        values["claude"].update(collect_claude_code(claude_homes, first, cutoff, timezone))
    if codex_homes:
        metadata["openai"] = {"label": "OpenAI", "color": PALETTE[1]}
        values["openai"].update(collect_codex(codex_homes, first, cutoff, timezone))
    for source in json_sources:
        merge_json_source(source, values, metadata)
    for source in csv_sources:
        merge_csv_source(source, values, metadata)

    dates = [first + timedelta(days=index) for index in range(days)]
    series = []
    for index, provider_id in enumerate(metadata):
        meta = metadata[provider_id]
        daily = [values[provider_id][day] for day in dates]
        if not any(daily):
            continue
        series.append({
            "id": provider_id,
            "label": meta.get("label") or provider_id.title(),
            "color": meta.get("color") or PALETTE[index % len(PALETTE)],
            "daily": daily,
        })

    now = datetime.now(timezone) if timezone else datetime.now().astimezone()
    return {
        "schema_version": 2,
        "generated": now.isoformat(timespec="minutes"),
        "dates": [day.isoformat() for day in dates],
        "series": series,
        "counting": {"cache": "mixed" if json_sources or csv_sources else "excluded"},
    }


def atomic_write(path: Path, data) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14, help="calendar days to emit (default: 14)")
    parser.add_argument("--output", type=Path, default=Path("data.json"))
    parser.add_argument("--timezone", help="IANA timezone, e.g. Europe/Berlin")
    parser.add_argument("--no-auto", action="store_true", help="do not auto-detect ~/.claude and ~/.codex")
    parser.add_argument("--claude-home", type=Path, action="append", default=[])
    parser.add_argument("--codex-home", type=Path, action="append", default=[])
    parser.add_argument("--json", action="append", default=[], help="merge schema-v2 JSON file or URL")
    parser.add_argument("--csv", action="append", default=[], help="merge CSV file or URL")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.days < 1:
        print("--days must be at least 1", file=sys.stderr)
        return 2
    try:
        timezone = ZoneInfo(args.timezone) if args.timezone else None
    except ZoneInfoNotFoundError:
        print(f"unknown timezone: {args.timezone}", file=sys.stderr)
        return 2

    claude_homes = [path.expanduser().resolve() for path in args.claude_home]
    codex_homes = [path.expanduser().resolve() for path in args.codex_home]
    if not args.no_auto:
        for collection, candidate in ((claude_homes, Path("~/.claude").expanduser()),
                                      (codex_homes, Path("~/.codex").expanduser())):
            resolved = candidate.resolve()
            if resolved.exists() and resolved not in collection:
                collection.append(resolved)

    today = datetime.now(timezone).date() if timezone else date.today()
    try:
        data = build_data(
            args.days, today, timezone, claude_homes, codex_homes, args.json, args.csv
        )
        atomic_write(args.output, data)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"collector error: {error}", file=sys.stderr)
        return 1
    totals = {item["label"]: sum(item["daily"]) for item in data["series"]}
    print(f"wrote {args.output}: {totals or 'no usage found'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
