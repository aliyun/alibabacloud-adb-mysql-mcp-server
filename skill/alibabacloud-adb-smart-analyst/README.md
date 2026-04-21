# ADB Smart Analyst - Quick Start Guide

## 🚀 Configure Database Connection

Database connection is managed via **environment variables**, effective only in the current shell session and never written to files.

For first-time use, simply ask the AI:

> "Query last month's gross profit by channel"

The AI will automatically detect whether the environment variables are set. If not, it will guide you to run the following in your terminal:

```bash
export ADB_MYSQL_HOST=<your database address, e.g. amv-xxx.ads.aliyuncs.com>
export ADB_MYSQL_USER=<your username>
export ADB_MYSQL_PASSWORD=<your password>
export ADB_MYSQL_PORT=3306
```

After running the commands, inform the AI and it will continue processing your original request.

> ⚠️ **Security Note**: Environment variables are only effective in the current shell session. They are not persisted to disk or committed to Git. You need to re-run the commands when opening a new terminal.

---

## 📋 Complete Workflow Example

### Scenario: Query Sales Revenue in Asia for 1995

```bash
# Locate the skill directory
SKILL_DIR="$(find ~ -maxdepth 3 -name 'alibabacloud-adb-smart-analyst' -type d 2>/dev/null | grep -m1 alibabacloud-adb-smart-analyst)"

# Step 1: Semantic Search - Find metric YAML definitions
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py search_metrics_rag "revenue asia" --attempt 1
```

Step 1 returns JSON where `data[].definition` is a YAML string. **Key fields**:

| YAML Field | Description | Usage |
|------------|-------------|-------|
| `tables[].base_table` | Actual **physical tables** | Pass to Step 2 for validation |
| `metrics` | Metric calculation formulas | Write into SQL SELECT |
| `dimensions` | Available dimension columns | Use in GROUP BY / WHERE |
| `relationships` | Table join conditions | Use in JOIN / WHERE |

```bash
# Step 2: Physical Alignment - Use physical tables from base_table, NOT semantic view names!
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py get_batch_table_metadata \
  '[{"catalog":"adb_catalog","schema":"tpch","table":"lineitem"},{"schema":"tpch","table":"region"}]' \
  --attempt 1

# Step 3: SQL Execution
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql \
  "SELECT r.r_name AS region, SUM(l.l_extendedprice) AS revenue FROM adb_catalog.tpch.lineitem l JOIN tpch.region r ON l.l_regionkey = r.r_regionkey WHERE r.r_name = 'ASIA' GROUP BY r.r_name" \
  --attempt 1
```

---

## 🔧 Command Reference

All functions are accessed through the unified entry point `scripts/adb_smart_analyst.py`.

### search_metrics_rag (Step 1: Semantic Search)

```bash
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py search_metrics_rag "keyword" [--top-k 5] --attempt N
```

| Parameter | Description |
|-----------|-------------|
| `query` | Business keyword (English), e.g. "revenue", "profit margin" (positional argument) |
| `--top-k` | Number of results to return, default 5 |
| `--attempt` | Current attempt number (1-3); attempt 3 triggers full fallback |

---

### get_batch_table_metadata (Step 2: Physical Alignment)

```bash
# JSON array format
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py get_batch_table_metadata \
  '[{"catalog":"c","schema":"db","table":"t1"},{"schema":"db","table":"t2"}]' \
  --attempt N
```

| Parameter | Description |
|-----------|-------------|
| `tables` | Required, JSON array with catalog (optional) / schema (required) / table (required) |
| `--attempt` | Current attempt number (1-3) |

---

### execute_adb_sql (Step 3: SQL Execution)

```bash
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql "SELECT ..." --attempt N
```

| Parameter | Description |
|-----------|-------------|
| `sql` | SQL statement (positional argument) |
| `--attempt` | Current attempt number (1-3) |

---

### create_semantic_view (Create Semantic View)

```bash
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py create_semantic_view "schema.view_name" "yaml_content"
```

---

## 🎯 How to Trigger the AI to Use This Skill

### Good Queries (AI will invoke this Skill)
- "Query last month's gross margin by channel"
- "Show year-over-year GMV growth"
- "Rank inventory turnover by category"
- "Analyze order volume trends in East China over the past 30 days"

### Less Precise Queries
- "Help me look up some data" (missing metric and dimension keywords)
- "What tables are in ADB?" (metadata exploration, not a data query)

---

## 📊 3x3 Self-Healing Mechanism

Each stage allows up to 3 attempts. The `--attempt N` parameter is incremented by the Agent:

| Stage | attempt=1 | attempt=2 | attempt=3 | Exceeded |
|-------|-----------|-----------|-----------|----------|
| **Step 1** | Original keywords | Split / synonyms | Full fallback triggered | Return error |
| **Step 2** | Validate physical table columns | Try alternative columns | Fall back to Step 1 re-search | Return error |
| **Step 3** | Execute SQL | Fix columns / syntax | Reconstruct SQL from YAML | Return error |

---

## 🔍 Troubleshooting

### Database Connection Failure

```bash
# Check if environment variables are set
echo "ADB_MYSQL_HOST=${ADB_MYSQL_HOST:-(not set)}"

# Re-set environment variables
export ADB_MYSQL_HOST=<host>
export ADB_MYSQL_USER=<user>
export ADB_MYSQL_PASSWORD=<password>
export ADB_MYSQL_PORT=3306
```

### Step 1 Returns Empty Results

```sql
-- Directly check which semantic views exist
SELECT view_name, view_schema FROM information_schema.semantic_views LIMIT 20;
```

On the 3rd call (`--attempt 3`), a **full fallback** is automatically triggered, returning all semantic view records.

### Step 2 Cannot Find Columns

Ensure you are passing **physical tables** from `base_table`, not semantic view names:

```bash
# ✅ Correct: Pass physical table
'[{"catalog":"adb_catalog","schema":"tpch","table":"lineitem"}]'

# ❌ Wrong: Pass semantic view name
'[{"table":"sales_view"}]'
```

---

## 📚 Related Documentation

- [SKILL.md](SKILL.md) - Complete Skill specification and workflow
- [examples.md](examples.md) - Scenario-based usage examples
- [scripts/adb_smart_analyst.py](scripts/adb_smart_analyst.py) - Core implementation code
