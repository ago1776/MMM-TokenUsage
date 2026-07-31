#!/usr/bin/env python3
"""Build MMM-TokenUsage data.json from local OpenClaw/Codex transcripts.

The collector is read-only. It never reads credentials and only writes aggregated
daily totals. Cache tokens are deliberately excluded:

* Claude CLI: input_tokens + output_tokens (Claude reports cache separately)
* Codex/OpenAI: input_tokens - cached_input_tokens + output_tokens
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_day(timestamp: str | None, timezone: ZoneInfo | None) -> date | None:
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return parsed.astimezone(timezone).date() if timezone else parsed.astimezone().date()
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


def collect_claude(claude_home: Path, first: date, cutoff: float, timezone):
    daily = defaultdict(int)
    seen = set()
    for path in glob.glob(str(claude_home / "projects" / "*" / "*.jsonl")):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
        except OSError:
            continue
        for event in read_jsonl(path):
            if event.get("type") != "assistant":
                continue
            day = parse_day(event.get("timestamp"), timezone)
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


def collect_openai_classic(openclaw_home: Path, first: date, cutoff: float, timezone):
    """Collect legacy wrapper usage as a fallback for days without Codex rollouts."""
    daily = defaultdict(int)
    seen = set()
    patterns = [
        openclaw_home / "agents" / "*" / "sessions" / "*.jsonl",
        openclaw_home / "agents" / "*" / "sessions" / "*.jsonl.reset.*",
    ]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(str(pattern)))
    for path in paths:
        if ".trajectory.jsonl" in path:
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                continue
        except OSError:
            continue
        for event in read_jsonl(path):
            message = event.get("message") or event
            model = message.get("model") or ""
            provider = message.get("provider") or event.get("provider") or ""
            if not model.startswith("gpt") and provider != "openai":
                continue
            day = parse_day(event.get("timestamp"), timezone)
            if day is None or day < first:
                continue
            usage = message.get("usage") or {}
            message_id = message.get("id") or event.get("id") or event.get("uuid")
            key = message_id or (
                event.get("timestamp"), model, usage.get("input"), usage.get("output"),
                usage.get("cacheRead"), usage.get("totalTokens"),
            )
            if key in seen:
                continue
            seen.add(key)
            daily[day] += (usage.get("input") or 0) + (usage.get("output") or 0)
    return daily


def collect_openai_codex(openclaw_home: Path, first: date, cutoff: float, timezone):
    """Collect authoritative per-call usage from native Codex rollout files."""
    daily = defaultdict(int)
    pattern = (
        openclaw_home / "agents" / "*" / "agent" / "codex-home"
        / "sessions" / "**" / "rollout-*.jsonl"
    )
    for path in glob.glob(str(pattern), recursive=True):
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
            day = parse_day(event.get("timestamp"), timezone)
            if day is None or day < first:
                continue
            usage = ((payload.get("info") or {}).get("last_token_usage") or {})
            if not usage:
                continue
            gross_input = usage.get("input_tokens") or 0
            cached_input = usage.get("cached_input_tokens") or 0
            output = usage.get("output_tokens") or 0  # reasoning is already included
            daily[day] += max(0, gross_input - cached_input) + output
    return daily


def collect_data(
    days: int,
    today: date,
    timezone: ZoneInfo | None,
    openclaw_home: Path,
    claude_home: Path,
):
    first = today - timedelta(days=days - 1)
    local_tz = timezone or datetime.now().astimezone().tzinfo
    cutoff = datetime.combine(first, dt_time.min, tzinfo=local_tz).timestamp()
    claude = collect_claude(claude_home, first, cutoff, timezone)
    classic = collect_openai_classic(openclaw_home, first, cutoff, timezone)
    codex = collect_openai_codex(openclaw_home, first, cutoff, timezone)
    dates = [first + timedelta(days=index) for index in range(days)]

    # Direct OpenClaw values can mirror the same Codex calls incompletely. Prefer
    # native rollouts for the whole day and never add both sources.
    openai = {day: codex[day] if codex[day] else classic[day] for day in dates}
    now = datetime.now(timezone) if timezone else datetime.now().astimezone()
    return {
        "schema_version": 1,
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "days": [day.strftime("%d.%m.") for day in dates],
        "claude_daily": [claude[day] for day in dates],
        "openai_daily": [openai[day] for day in dates],
        "openai_days": [day.strftime("%d.%m.") for day in dates if openai[day] > 0],
        "fallback_days": [],
        "counting": {
            "cache": "excluded",
            "claude": "input_tokens + output_tokens",
            "openai": "input_tokens - cached_input_tokens + output_tokens",
        },
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
    parser.add_argument("--days", type=int, default=14, help="number of calendar days (default: 14)")
    parser.add_argument("--output", type=Path, default=Path("data.json"), help="output data.json")
    parser.add_argument("--openclaw-home", type=Path, default=Path("~/.openclaw").expanduser())
    parser.add_argument("--claude-home", type=Path, default=Path("~/.claude").expanduser())
    parser.add_argument("--timezone", help="IANA timezone, e.g. Europe/Berlin (default: system local)")
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
    today = datetime.now(timezone).date() if timezone else date.today()
    data = collect_data(
        args.days, today, timezone, args.openclaw_home.expanduser(), args.claude_home.expanduser()
    )
    atomic_write(args.output, data)
    print(
        f"wrote {args.output}: Claude={sum(data['claude_daily'])}, "
        f"OpenAI={sum(data['openai_daily'])}, cache=excluded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
