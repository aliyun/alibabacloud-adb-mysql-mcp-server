---
name: alibabacloud-adb-openclaw-insight
description: >
  OpenClaw conversation log collection and deep insight analysis Skill. Collects OpenClaw
  session logs (JSONL format) in real time and pushes them to Alibaba Cloud AnalyticDB
  MySQL (ADB) for storage. Provides a three-layer insight analysis architecture:
  L1 Operational Efficiency (Token efficiency, session depth, tool chain analysis,
  high-cost attribution, anomaly detection), L2 User Behavior (intent classification,
  task complexity, success rate, prompt quality, topic clustering,
  retry detection, thinking depth, user maturity), and L3 Organizational Cognition
  (tech stack heatmap, knowledge gap discovery, best practice extraction, skill
  candidate discovery, narrative report generation). Powered by SQL + Python + LLM.
  Use this Skill when you need to monitor OpenClaw usage, analyze costs, understand
  user behavior patterns, or generate organizational intelligence reports.
---

# OpenClaw Logger Insight ADB Skill

Collect OpenClaw session logs in real time and push them to AnalyticDB MySQL. Analyze usage patterns with a three-layer insight architecture powered by **SQL + Python + LLM**.

## Prerequisites

- Python >= 3.10 (use `python` or `python3` depending on your system)
- An accessible Alibaba Cloud AnalyticDB MySQL instance
- OpenClaw deployed and generating session files (`~/.openclaw/agents/*/sessions/*.jsonl`) and logs (`/tmp/openclaw/openclaw-YYYY-MM-DD.log`)
- (Optional) An OpenAI-compatible or Anthropic LLM API endpoint for L2/L3 analysis

## Quick Start

```bash
# 1. Navigate to the Skill directory
cd openclaw-insight

# 2. Install dependencies
pip install -r requirements.txt
# If "pip" is not found, try: pip3 install -r requirements.txt

# 3. Copy and edit the configuration file
cp config.example.json config.json
# Edit config.json: fill in ADB connection details and (optionally) LLM API config

# 4. Initialize the database tables
python -m scripts.init_db
# If "python" is not found, try: python3 -m scripts.init_db

# 5. Start the service (collection + scheduled analysis)
python -m scripts.main
# If "python" is not found, try: python3 -m scripts.main
```

## CLI Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `collect` | `python -m scripts.main collect` | One-shot collection: collect all new data, save file offsets, then exit. Safe to call repeatedly from any scheduler. |
| `analyze` | `python -m scripts.main analyze` | Run full analysis (L1 → L2 → L3 → Final Report) |
| `final-report` | `python -m scripts.main final-report` | Fetch and print the latest final narrative report from DB |

Run analysis manually with a custom time range:

```bash
# Time format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS (e.g. "2026-03-13 02:04:09")
python -m scripts.analyze_usage --from "2026-03-01 00:00:00" --to "2026-03-10 23:59:59"
```

## Scheduled Collection via OpenClaw Cron

`python -m scripts.main collect` is the recommended way to keep data flowing into ADB. It runs a single collection pass, saves the file-offset checkpoint, and exits — making it safe to call repeatedly from any scheduler.

Register it as an OpenClaw cron job (example: every 5 minutes):

```json
{
  "cron": "*/5 * * * *",
  "command": "python -m scripts.main collect",
  "cwd": "/path/to/openclaw-insight"
}
```

Each invocation:
1. Scans new JSONL session files and daily log files since the last run
2. Inserts new records into ADB in batches
3. Saves the file-offset checkpoint (`.collect_state.json`) so the next run picks up exactly where this one left off
4. Exits cleanly — no background process to manage

## Configuration

See `config.example.json` for all options:

- **adb**: ADB connection (host, port, database, credentials, table name)
- **collection**: Collection parameters (interval, batch size, retention days)
- **filters**: Log filtering (minimum level, subsystem include/exclude)
- **llm**: LLM API configuration (endpoint, API key, model, concurrency, temperature)
- **analysis**: Analysis toggles (enableL1/L2/L3, analysis window days, max sessions for LLM)

> **Note**: L1 analysis runs without LLM. L2 and L3 require a configured LLM endpoint.

