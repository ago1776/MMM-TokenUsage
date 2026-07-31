# MMM-TokenUsage

A provider-neutral [MagicMirror²](https://magicmirror.builders/) module that shows daily
AI token usage as stacked gradient bars. It can render any number of providers and reads
either a local JSON file or an HTTP(S) JSON feed.

![MMM-TokenUsage screenshot](screenshot.png)

The renderer does not need an AI runtime, provider account or API key. It only consumes the
small public data contract in [`data.schema.json`](data.schema.json). Legacy v1 files with
fixed Claude/OpenAI arrays remain supported.

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
  config: {
    dataSource: "data.json"
  }
}
```

`dataSource` can be a file relative to the module directory or an HTTP(S) URL:

```js
config: {
  dataSource: "http://192.168.1.20:8080/token-usage.json"
}
```

## Easiest local setup

The optional standard-library collector auto-detects Claude Code (`~/.claude`) and Codex
(`~/.codex`). Run it on the machine that owns those transcripts:

```bash
python3 collectors/collect.py \
  --timezone Europe/Berlin \
  --output data.json
```

Cache is excluded by the built-in adapters:

- Claude Code: `input_tokens + output_tokens`
- Codex: `input_tokens - cached_input_tokens + output_tokens`

Custom locations are explicit and repeatable:

```bash
python3 collectors/collect.py --no-auto \
  --claude-home /srv/ai/claude \
  --codex-home /srv/ai/codex-personal \
  --codex-home /srv/ai/codex-work \
  --output data.json
```

The collector never reads credentials and never modifies transcript directories.

## Connect any other provider

Provider APIs and clients expose usage in different ways, so the module uses two neutral
inputs instead of requiring provider secrets on the mirror.

### CSV: simplest adapter

Create or export a CSV with three required columns. `label` and `color` are optional:

```csv
date,provider,tokens,label,color
2026-01-13,gemini,24500,Gemini,#8abf69
2026-01-13,openrouter,18000,OpenRouter,#b58ad8
2026-01-14,mistral,9200,Mistral,#e0a84f
```

Merge any number of local files or URLs:

```bash
python3 collectors/collect.py \
  --csv provider-export.csv \
  --csv https://usage.example.net/team.csv \
  --output data.json
```

### JSON: native multi-provider feed

The v2 format supports arbitrary series:

```json
{
  "schema_version": 2,
  "generated": "2026-01-14T07:00:00+01:00",
  "dates": ["2026-01-13", "2026-01-14"],
  "series": [
    {
      "id": "gemini",
      "label": "Gemini",
      "color": "#8abf69",
      "daily": [24500, 12000]
    },
    {
      "id": "openrouter",
      "label": "OpenRouter",
      "daily": [18000, 9000]
    }
  ]
}
```

Use a feed directly as `dataSource`, or merge it with local/client data:

```bash
python3 collectors/collect.py \
  --json https://usage.example.net/token-usage.json \
  --output data.json
```

This makes the display compatible with provider billing APIs, gateways, exporters and
future clients without changing the MagicMirror module. A tiny scheduled script only needs
to emit CSV or schema-v2 JSON.

## Collector and mirror on different machines

Run the collector where the usage data exists and transfer only the aggregate JSON. No
transcripts or credentials belong on the mirror:

```bash
python3 collectors/collect.py --output /tmp/token-usage.json
scp /tmp/token-usage.json mirror-host:/tmp/token-usage.json
ssh mirror-host 'install -m 0644 /tmp/token-usage.json ~/MagicMirror/modules/MMM-TokenUsage/data.json'
```

Alternatively expose the aggregate JSON through an existing internal web server and set
`dataSource` to its URL.

## Daily systemd timer

```bash
mkdir -p ~/.config/systemd/user
cp examples/systemd/mmm-tokenusage-collector.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mmm-tokenusage-collector.timer
systemctl --user start mmm-tokenusage-collector.service
```

The sample service expects `~/MagicMirror/modules/MMM-TokenUsage`, uses `Europe/Berlin`,
and auto-detects the standard Claude Code/Codex locations. Adjust its command as needed.

## Configuration

| Option           | Type   | Default                 | Description |
| ---------------- | ------ | ----------------------- | ----------- |
| `header`         | string | `"AI Usage · 14 days"` | Module header. |
| `updateInterval` | number | `900000`                | Refresh interval in milliseconds. |
| `dataSource`     | string | `"data.json"`          | Relative JSON file or HTTP(S) URL. |
| `barMaxHeight`   | number | `96`                    | Height of the tallest bar in pixels. |
| `providerColors` | object | `{}`                    | Optional colour overrides keyed by provider id. |

Example colour override:

```js
providerColors: {
  gemini: "#4285f4",
  openrouter: "#7b61ff"
}
```

## License

MIT © Andreas Göpfert
