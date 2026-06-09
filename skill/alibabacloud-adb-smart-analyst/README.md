# ADB Smart Analyst - Quick Start Guide

## Configure Database Connection

Database connection is managed via **environment variables**, effective only in the current shell session and never written to files.

For first-time use, simply ask the AI:

> "Query last month's gross profit by channel"

The AI will automatically detect whether the environment variables are set. If not, it will guide you to run the following in your terminal:

```bash
export ADB_MYSQL_HOST=<your ADB MySQL address, e.g. amv-xxx.ads.aliyuncs.com>
export ADB_MYSQL_PORT=3306
export ADB_MYSQL_DATABASE=<default database>
export ADB_MYSQL_USER=<your username>
export ADB_MYSQL_PASSWORD=<your password>
```

After running the commands, inform the AI and it will continue processing your original request.

> **Security Note**: Environment variables are only effective in the current shell session. They are not persisted to disk or committed to Git. You need to re-run the commands when opening a new terminal.

### Optional: OpenAPI Mode

When SQL-based semantic features are unavailable, the skill automatically falls back to OpenAPI mode. This requires:

- **aliyun CLI** installed with the **adb** plugin
- **Credentials** configured via `aliyun configure`
- Environment variable: `ADB_CLUSTER_ID=<your cluster ID, e.g. am-bp1xxxxxxxx>`
- Optional: `ADB_REGION=<region, e.g. cn-hangzhou>`

Data execution still goes through the SQL connection — OpenAPI is only used for semantic operations.

### Dependencies

```bash
uv pip install pymysql
# Optional (only needed for caching_sha2_password or TLS):
uv pip install cryptography
```

---

## Architecture

```
Mode A (Primary — Full SQL):
  User → Agent → Skill → PyMySQL → ADB Engine

Mode B (OpenAPI Semantic + SQL Execution):
  Semantic ops: User → Agent → Skill → aliyun CLI → OpenAPI Gateway → ADB Engine
  Data execution: User → Agent → Skill → PyMySQL → ADB Engine
```

The skill prefers SQL mode and automatically falls back to OpenAPI when SQL semantic features are unavailable.

---

## Two-Phase Query Flow

### Phase 1 — Intent Anchoring

1. Extract keywords from user's question
2. Search semantic views: `search_semantic_views --keywords "keyword1 keyword2" --top-k 3`
3. Decompose question into **target metrics** and **filter conditions**
4. Map user keywords to semantic objects (dimensions, facts, metrics) in candidate views
5. Select the best-matching view or ask the user to clarify

### Phase 2 — Deterministic Execution

1. Generate semantic SQL based on the selected view's YAML definition
2. Execute via `execute_sql` (semantic rewrite enabled by default)
3. Present: data table, semantic SQL + rewritten SQL, analysis, visualization suggestions

---

## Complete Workflow Example

### Scenario: Query Sales Revenue in Beijing for 2025

```bash
# Step 1: Search semantic views
uv run scripts/adb_analyst.py search_semantic_views --keywords "Beijing sales" --top-k 3

# Step 2: Execute semantic SQL (AGG() wraps metrics, engine maps to actual aggregation)
uv run scripts/adb_analyst.py execute_sql --sql "SELECT city, order_year, AGG(total_revenue), AGG(order_count) FROM sales_db.SALES_ANALYSIS WHERE city = 'Beijing' AND order_year = 2025 GROUP BY city, order_year LIMIT 100"
```

---

## Command Reference

All functions are accessed through `scripts/adb_analyst.py`.

### search_semantic_views

Search semantic views by keyword similarity.

```bash
uv run scripts/adb_analyst.py search_semantic_views --keywords "sales revenue" --top-k 3
```

| Parameter | Description |
|-----------|-------------|
| `--keywords` | Space-separated search keywords (required) |
| `--top-k` | Number of results to return (default: 3) |

### get_semantic_view

Retrieve semantic view definitions.

```bash
uv run scripts/adb_analyst.py get_semantic_view --schema sales_db --view-name SALES_ANALYSIS
```

| Parameter | Description |
|-----------|-------------|
| `--schema` | Filter by schema |
| `--view-name` | Filter by view name (requires `--schema`) |

### execute_sql

Execute SQL queries in semantic mode (default) or direct mode.

```bash
# Semantic mode (default) — SQL hints added automatically
uv run scripts/adb_analyst.py execute_sql --sql "SELECT city, AGG(revenue) FROM sales_db.VIEW GROUP BY city LIMIT 100"

# Direct mode — skip semantic rewrite, for data exploration
uv run scripts/adb_analyst.py execute_sql --sql "SELECT * FROM sales_db.orders WHERE dt >= '2026-05-01' LIMIT 10" --no-semantic-rewrite
```

| Parameter | Description |
|-----------|-------------|
| `--sql` | SQL statement (required) |
| `--no-semantic-rewrite` | Skip semantic rewrite, use direct mode |
| `--max-rows` | Max rows to return (default: 500, capped at 100 in direct mode) |

### create_semantic_view

```bash
uv run scripts/adb_analyst.py create_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --yaml-file /tmp/view.yaml
```

| Parameter | Description |
|-----------|-------------|
| `--schema` | Target schema (required) |
| `--view-name` | View name (required) |
| `--yaml-file` | Path to YAML definition file, use `-` for stdin (required) |
| `--or-replace` | Add OR REPLACE clause |
| `--if-not-exists` | Add IF NOT EXISTS clause |

### alter_semantic_view

```bash
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name VIEW --operation rename --new-name NEW_VIEW
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name VIEW --operation set_comment --comment "Updated view"
```

### drop_semantic_view

```bash
uv run scripts/adb_analyst.py drop_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS
```

### list_databases

```bash
uv run scripts/adb_analyst.py list_databases
```

### explore_table_metadata

Explore physical table structure, statistics, and sample data.

```bash
uv run scripts/adb_analyst.py explore_table_metadata --operation <op> --database <db> [--table <tbl>] [options]
```

| Operation | Description | Requires `--table` |
|-----------|-------------|-------------------|
| `list_tables` | List all tables in a database | No |
| `describe_table` | Show column structure | Yes |
| `table_statistics` | Row count and data size | Yes |
| `partition_info` | Partition key and partition stats | Yes |
| `index_info` | Index information | Yes |
| `show_create_table` | Show CREATE TABLE DDL | Yes |
| `safe_sample` | Partition-aware sampling | Yes |
| `explain` | Show query execution plan | Yes (+ `--sql`) |

---

## How to Trigger the AI to Use This Skill

### Good Queries
- "Query last month's gross margin by channel"
- "Show year-over-year GMV growth"
- "Rank inventory turnover by category"
- "Analyze order volume trends in East China over the past 30 days"
- "Create a semantic view for logistics analysis"
- "What tables are in the logistics database?"

### Degradation to Exploration Mode
When no semantic view matches, the skill automatically degrades to exploration mode with a four-stage flow: Schema discovery → Table discovery → Structure analysis → Safe sampling & query.

---

## Troubleshooting

### Database Connection Failure

```bash
# Check if environment variables are set
echo "ADB_MYSQL_HOST=${ADB_MYSQL_HOST:-(not set)}"
echo "ADB_MYSQL_USER=${ADB_MYSQL_USER:-(not set)}"

# Re-set environment variables
export ADB_MYSQL_HOST=<host>
export ADB_MYSQL_PORT=3306
export ADB_MYSQL_DATABASE=<database>
export ADB_MYSQL_USER=<user>
export ADB_MYSQL_PASSWORD=<password>
```

### Semantic Search Returns No Results

```bash
# List available databases
uv run scripts/adb_analyst.py list_databases

# Browse all semantic views in a schema
uv run scripts/adb_analyst.py get_semantic_view --schema sales_db
```

If no semantic views match after 3 clarification rounds, the skill degrades to data exploration mode.

### Semantic SQL Errors

- Ensure metrics use `AGG()` wrapper: `AGG(total_revenue)`, not `SUM(total_revenue)`
- WHERE clauses can only use dimensions or facts, not metrics
- HAVING clauses can only use metrics
- Field names must match the `name` field in the YAML definition
- Always include `LIMIT`

---

## Related Documentation

- [SKILL.md](SKILL.md) - Complete skill specification and workflow
- [examples.md](examples.md) - Scenario-based usage examples
- [scripts/adb_analyst.py](scripts/adb_analyst.py) - Core implementation code
