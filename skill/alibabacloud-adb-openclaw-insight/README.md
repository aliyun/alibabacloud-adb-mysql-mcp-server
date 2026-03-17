# ADB MySQL OpenClaw Insight - OpenClaw Skill

A skill for collecting [OpenClaw](https://openclaw.io) session logs in real time and pushing them to Alibaba Cloud [AnalyticDB for MySQL (ADB MySQL)](https://adb.console.aliyun.com/adb/cn-hangzhou/summary) for storage and deep analysis. Provides a three-layer insight architecture powered by **SQL + Python + LLM** to help teams understand AI usage patterns, control costs, and extract organizational intelligence.

## 一、Features

- **L1 Operational Efficiency**: Token efficiency analysis, session depth distribution, tool chain pattern mining, high-cost task chain attribution, anomaly detection — all powered by pure SQL + Python, no LLM required
- **L2 User Behavior**: Intent classification, task complexity scoring, success rate estimation, prompt quality evaluation, topic clustering, retry detection, thinking depth analysis, user maturity profiling — powered by LLM
- **L3 Organizational Cognition**: Tech stack heatmap, knowledge gap discovery, best practice extraction, skill candidate discovery, narrative report generation — powered by LLM
- **Real-time Log Collection**: Continuously collects OpenClaw JSONL session files and daily log files, with file-offset checkpointing to avoid duplicate ingestion
- **Scheduled Collection**: Integrates with OpenClaw cron for fully automated, incremental data collection
- **Flexible Analysis Window**: Run analysis on any custom time range via CLI
- **Zero-LLM Mode**: L1 analysis runs entirely without an LLM endpoint

## 二、Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip / pip3
- An accessible Alibaba Cloud AnalyticDB MySQL instance
- OpenClaw deployed and generating session files (`~/.openclaw/agents/*/sessions/*.jsonl`) and log files (`/tmp/openclaw/openclaw-YYYY-MM-DD.log`)
- *(Optional)* An OpenAI-compatible or Anthropic LLM API endpoint for L2/L3 analysis

## 三、Quick Start

### 3.1 Clone the repository

```bash
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server/skill/alibabacloud-adb-openclaw-insight
```

### 3.2 Install uv (recommended)

[uv](https://docs.astral.sh/uv/) is a fast Python package manager that handles virtual environments automatically.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3.3 Install dependencies

**Using uv (recommended):**

```bash
uv pip install -r requirements.txt
```

**Using pip:**

```bash
pip install -r requirements.txt
# If "pip" is not found, try:
pip3 install -r requirements.txt
```

### 3.3 Configure

```bash
cp config.example.json config.json
```

Edit `config.json` and fill in your ADB connection details and (optionally) your LLM API config. Key fields:

| Section | Key Fields | Description |
|---------|-----------|-------------|
| `adb` | `host`, `port`, `database`, `username`, `password` | ADB MySQL connection info |
| `collection` | `intervalMinutes`, `batchSize`, `retentionDays` | Collection behavior |
| `filters` | `minLevel`, `includeSubsystems`, `excludeSubsystems` | Log filtering rules |
| `llm` | `endpoint`, `apiKey`, `model` | LLM API for L2/L3 analysis |
| `analysis` | `enableL1`, `enableL2`, `enableL3`, `analysisWindowDays` | Analysis toggles |

> **Note**: L1 analysis runs without LLM. L2 and L3 require a configured `llm` endpoint.

### 3.4 Initialize the database

```bash
python -m scripts.init_db
# If "python" is not found, try:
python3 -m scripts.init_db
```

### 3.5 Start the service

```bash
python -m scripts.main
# If "python" is not found, try:
python3 -m scripts.main
```

## 四、CLI Commands

| Command | Usage | Description |
|---------|-------|-------------|
| *(default)* | `python -m scripts.main` | Start the service: collection + scheduled analysis |
| `collect` | `python -m scripts.main collect` | One-shot collection: collect all new data, save file offsets, then exit |
| `analyze` | `python -m scripts.main analyze` | Run full analysis (L1 → L2 → L3 → Final Report) |
| `final-report` | `python -m scripts.main final-report` | Fetch and print the latest final narrative report from DB |

Run analysis on a custom time range:

```bash
# Time format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
python -m scripts.analyze_usage --from "2026-03-01 00:00:00" --to "2026-03-10 23:59:59"
```

## 五、Scheduled Collection via OpenClaw Cron

`python -m scripts.main collect` is the recommended way to keep data flowing into ADB. It runs a single collection pass, saves the file-offset checkpoint, and exits — making it safe to call repeatedly from any scheduler.

Register it as an OpenClaw cron job (example: every 5 minutes):

```json
{
  "cron": "*/5 * * * *",
  "command": "python -m scripts.main collect",
  "cwd": "/path/to/alibabacloud-adb-openclaw-insight"
}
```

Each invocation:
1. Scans new JSONL session files and daily log files since the last run
2. Inserts new records into ADB in batches
3. Saves the file-offset checkpoint (`.collect_state.json`) so the next run picks up exactly where this one left off
4. Exits cleanly — no background process to manage

## 六、Analysis Architecture

```
Raw OpenClaw Logs (JSONL + .log)
        │
        ▼
  ADB MySQL Storage
        │
        ├─► L1 Operational Efficiency  (SQL + Python, no LLM)
        │     ├─ Token efficiency & cache hit rate
        │     ├─ Session depth distribution
        │     ├─ Tool chain pattern mining (bigrams / trigrams)
        │     ├─ High-cost task chain attribution
        │     └─ Anomaly detection (z-score + off-hours)
        │
        ├─► L2 User Behavior           (LLM required)
        │     ├─ Intent classification & task complexity
        │     ├─ Success rate & prompt quality
        │     ├─ Topic clustering & retry detection
        │     └─ User maturity profiling
        │
        └─► L3 Organizational Cognition (LLM required)
              ├─ Tech stack heatmap & knowledge gap discovery
              ├─ Best practice extraction
              ├─ Skill candidate discovery
              └─ Narrative report generation
```

## 七、Troubleshooting

### 7.1 Missing dependencies

If you see `ImportError` or `ModuleNotFoundError`, install dependencies manually:

```bash
pip install mysql-connector-python APScheduler openai anthropic
```

### 7.2 Cannot connect to ADB

Verify your `config.json` connection fields and ensure the ADB instance is accessible from your network (check whitelist / VPC settings):

```bash
mysql -h <host> -P <port> -u <username> -p <database>
```

### 7.3 L2/L3 analysis not running

Ensure `enableL2` / `enableL3` are set to `true` in `config.json` and that a valid `llm.apiKey` and `llm.endpoint` are configured.

### 7.4 No data collected

Check that OpenClaw is running and generating files at:
- `~/.openclaw/agents/*/sessions/*.jsonl`
- `/tmp/openclaw/openclaw-YYYY-MM-DD.log`

Also verify the `filters.minLevel` setting is not filtering out all log entries.
