# MMM-TokenUsage

A [MagicMirror²](https://magicmirror.builders/) module that shows **daily AI token usage**
as stacked gradient bars over the last two weeks — one series for Claude, one for OpenAI —
plus a legend, a total and a "today" figure. Weekends are marked and optional annotations
can be shown below the chart.

![MMM-TokenUsage screenshot](screenshot.png)

The module remains a **pure renderer**. A sample `data.json` is included, and an optional,
read-only OpenClaw/Codex collector is provided so users do not have to invent the counting
logic themselves.

## Installation

```bash
cd ~/MagicMirror/modules
git clone https://github.com/ago1776/MMM-TokenUsage
```

```js
{
  module: "MMM-TokenUsage",
  position: "top_right",
  header: "AI Usage · 14 days",
  config: { }
}
```

## OpenClaw in five minutes (optional collector)

Run this on the machine that owns the OpenClaw transcripts. It reads `~/.openclaw` and
`~/.claude`, then atomically writes aggregate daily totals:

```bash
cd ~/MagicMirror/modules/MMM-TokenUsage
python3 collectors/openclaw.py \
  --timezone Europe/Berlin \
  --output data.json
```

The collector uses only Python's standard library. It never reads credentials and never
writes to transcript directories.

### Counting semantics

Cache is excluded by default and is not displayed:

- Claude CLI: `input_tokens + output_tokens` (Claude reports cache separately).
- Native Codex/OpenAI: `input_tokens - cached_input_tokens + output_tokens`.
- OpenClaw's direct `gpt-*` session values are used only for days without native Codex
  rollouts. Both sources are never added because the wrapper can represent the same calls
  incompletely.
- Session reset archives are read and deduplicated, so historical totals do not disappear.
- OpenAI usage does **not** imply that Claude hit a limit; users can select an OpenAI model
  manually.

Use `--days`, `--openclaw-home`, `--claude-home`, and `--timezone` to override defaults.
Run `python3 collectors/openclaw.py --help` for all options.

### Daily systemd timer (same host)

```bash
mkdir -p ~/.config/systemd/user
cp examples/systemd/mmm-tokenusage-collector.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mmm-tokenusage-collector.timer
systemctl --user start mmm-tokenusage-collector.service
```

The sample service expects the standard path `~/MagicMirror/modules/MMM-TokenUsage` and
uses `Europe/Berlin`; adjust both before enabling it.

### MagicMirror and OpenClaw on different hosts

Clone this repository (or copy `collectors/openclaw.py`) to the OpenClaw host. Run the
collector there and transfer only the aggregate JSON:

```bash
python3 collectors/openclaw.py --timezone Europe/Berlin --output /tmp/token-usage.json
scp /tmp/token-usage.json mirror-host:/tmp/token-usage.json
ssh mirror-host 'install -m 0644 /tmp/token-usage.json ~/MagicMirror/modules/MMM-TokenUsage/data.json'
```

Use a restricted SSH account/path in production. No transcripts or credentials need to be
copied to the mirror.

## Data format (`data.json`)

Place a `data.json` in the module folder (your feeder overwrites it):

```json
{
  "schema_version": 1,
  "generated": "2026-01-14 07:00",
  "days": ["01.01.", "02.01.", "…", "14.01."],
  "claude_daily": [210000, 180000, 340000, "… 14 values, oldest → newest"],
  "openai_daily": [0, 0, 0, "… 14 values"],
  "fallback_days": []
}
```

- `claude_daily` / `openai_daily`: arrays of equal length (e.g. 14), oldest day first.
- `generated`: timestamp of the newest day (used to place weekday markers).
- `days`: optional labels for feeders and diagnostics.
- `fallback_days`: optional presentation metadata shown as a footnote. The bundled collector
  leaves it empty because model usage alone cannot prove a provider fallback.
- `counting`: optional metadata describing feeder semantics; ignored by the renderer.

The machine-readable contract is in [`data.schema.json`](data.schema.json).

## Configuration options

| Option           | Type   | Default              | Description                                 |
| ---------------- | ------ | -------------------- | ------------------------------------------- |
| `header`         | string | `"AI Usage · 14 days"` | Module header (via MagicMirror `header`). |
| `updateInterval` | number | `900000` (15 min)    | How often `data.json` is re-read (ms).      |
| `barMaxHeight`   | number | `96`                 | Height of the tallest bar in px.            |
| `colorClaude`    | string | `"#c96f4a"`          | Bar colour for the first series.            |
| `colorOpenAI`    | string | `"#5aa6d8"`          | Bar colour for the second series.           |

## License

MIT © Andreas Göpfert
