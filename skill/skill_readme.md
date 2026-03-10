# ADB MySQL Copilot - Claude Code Skill

A Claude Code skill for Alibaba Cloud [AnalyticDB for MySQL (ADB MySQL)](https://www.alibabacloud.com/zh/product/analyticdb-for-mysql). Enables AI-assisted cluster management, performance monitoring, slow query diagnosis, and SQL execution directly within Claude conversations.

## 一、Features

- **Cluster Management**: List clusters, view detailed attributes, storage space summary, accounts, and network info
- **Performance Monitoring**: Query CPU, memory, QPS, RT, connections, disk usage, and other metrics
- **Slow Query Diagnosis**: Detect BadSQL, analyze SQL Patterns, locate slow query root causes with guided diagnostic workflows
- **Running SQL Analysis**: Inspect currently executing queries, identify resource-heavy operations
- **Table Analysis**: Table statistics, optimization advices, excessive primary keys, oversized non-partition tables, partition diagnosis, data skew detection
- **SQL Execution**: Execute diagnostic SQL directly against the database (requires database connection credentials)
- **Diagnostic Scenarios**: Built-in guided workflows for common scenarios (slow query triage, cluster inspection, SQL-based diagnostics)
- **Zero Installation**: Uses `uv run` with inline script dependencies — no `pip install` needed

## 二、Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Alibaba Cloud Access Key with ADB MySQL permissions

## 三、Quick Start

### 3.1 Clone the repository

```bash
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server/skill
```

### 3.2 Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3.3 Set environment variables

**macOS / Linux:**

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="your-access-key-id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your-access-key-secret"
# Optional: STS token for temporary credentials
# export ALIBABA_CLOUD_SECURITY_TOKEN="your-sts-token"
# Optional: Direct database connection (for execute_sql)
# export ADB_MYSQL_HOST="your_host"
# export ADB_MYSQL_PORT="3306"
# export ADB_MYSQL_USER="your_username"
# export ADB_MYSQL_PASSWORD="your_password"
# export ADB_MYSQL_DATABASE="your_database"
```

**Permanent configuration (recommended):**

Add the above to your shell config file (`~/.bashrc`, `~/.zshrc`, etc.).

### 3.4 Deploy to Claude Code

Copy the skill directory to the Claude Code skills folder:

```bash
# macOS / Linux
mkdir -p ~/.claude/skills/
cp -r alibabacloud-adb-mysql-copilot ~/.claude/skills/
```

Or create a symbolic link (recommended for development):

```bash
mkdir -p ~/.claude/skills/
ln -s "$(pwd)/alibabacloud-adb-mysql-copilot" ~/.claude/skills/alibabacloud-adb-mysql-copilot
```

### 3.5 Verify installation

Launch Claude Code and invoke the skill:

```bash
claude
```

```bash
/alibabacloud-adb-mysql-copilot How many ADB MySQL clusters do I have in cn-hangzhou?
```

Or verify the script directly:

```bash
uv run ~/.claude/skills/alibabacloud-adb-mysql-copilot/scripts/call_adb_api.py \
    describe_db_clusters --region cn-hangzhou
```

## 四、Usage Examples

```bash
# List clusters
uv run ./scripts/call_adb_api.py describe_db_clusters --region cn-hangzhou

# Get cluster details
uv run ./scripts/call_adb_api.py describe_db_cluster_attribute --cluster-id amv-xxx

# Query CPU performance (last 1 hour by default)
uv run ./scripts/call_adb_api.py describe_db_cluster_performance \
    --cluster-id amv-xxx --key AnalyticDB_CPU

# Detect bad SQL
uv run ./scripts/call_adb_api.py describe_bad_sql_detection --cluster-id amv-xxx

# Query running SQL
uv run ./scripts/call_adb_api.py describe_diagnosis_records --cluster-id amv-xxx \
    --query-condition '{"Type":"status","Value":"running"}'

# SQL pattern analysis
uv run ./scripts/call_adb_api.py describe_sql_patterns --cluster-id amv-xxx

# Execute diagnostic SQL (requires ADB_MYSQL_* env vars)
uv run ./scripts/call_adb_api.py execute_sql --query "SHOW PROCESSLIST"
```

## 五、Troubleshooting

### 5.1 Missing dependencies

If you see `ImportError`, install dependencies manually:

```bash
pip install alibabacloud-adb20211201 alibabacloud-tea-openapi alibabacloud-tea-util pymysql
```

### 5.2 Credentials error

Ensure `ALIBABA_CLOUD_ACCESS_KEY_ID` and `ALIBABA_CLOUD_ACCESS_KEY_SECRET` are set correctly:

```bash
echo $ALIBABA_CLOUD_ACCESS_KEY_ID   # Should not be empty
echo $ALIBABA_CLOUD_ACCESS_KEY_SECRET  # Should not be empty
```

### 5.3 Skill not recognized by Claude Code

1. Verify the skill is in `~/.claude/skills/alibabacloud-adb-mysql-copilot/`
2. Ensure `SKILL.md` exists in the skill root directory
3. Restart Claude Code
