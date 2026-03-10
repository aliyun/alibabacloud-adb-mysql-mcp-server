# ADB MySQL Copilot - Claude Code 技能

阿里云 [AnalyticDB for MySQL (ADB MySQL)](https://www.alibabacloud.com/zh/product/analyticdb-for-mysql) 的 Claude Code 技能，用于在 Claude 对话中直接完成集群管理、性能监控、慢查询诊断和 SQL 执行等任务。

## 一、功能

- **集群管理**：查询集群列表、查看集群详细属性、存储空间概览、账号信息、网络信息
- **性能监控**：查询 CPU、内存、QPS、RT、连接数、磁盘使用等指标
- **慢查询诊断**：检测 BadSQL、分析 SQL Pattern、通过引导式诊断流程定位慢查询根因
- **运行中 SQL 分析**：查看当前正在执行的 SQL，识别资源消耗大的操作
- **表级分析**：表统计信息、优化建议、主键过多检测、超大未分区表检测、分区表诊断、数据倾斜检测
- **SQL 执行**：直连数据库执行诊断 SQL（需配置数据库连接信息）
- **诊断场景引导**：内置常见场景的诊断流程（慢查询排查、集群巡检、SQL 巡检与配置查看）
- **零安装**：使用 `uv run` 内联脚本依赖，无需额外 `pip install`

## 二、环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- 具有 ADB MySQL 权限的阿里云 Access Key

## 三、快速开始

### 3.1 克隆仓库

```bash
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server/skill
```

### 3.2 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3.3 配置环境变量

**macOS / Linux：**

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="你的AccessKey ID"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="你的AccessKey Secret"
# 可选：使用临时凭证时设置 STS Token
# export ALIBABA_CLOUD_SECURITY_TOKEN="你的STS Token"
# 可选：直连数据库执行 SQL（用于 execute_sql）
# export ADB_MYSQL_HOST="数据库地址"
# export ADB_MYSQL_PORT="3306"
# export ADB_MYSQL_USER="数据库用户名"
# export ADB_MYSQL_PASSWORD="数据库密码"
# export ADB_MYSQL_DATABASE="默认数据库名"
```

**永久配置（推荐）：**

将上述命令添加到 shell 配置文件中（`~/.bashrc`、`~/.zshrc` 等）。

### 3.4 部署到 Claude Code

将技能目录拷贝到 Claude Code 的技能目录：

```bash
# macOS / Linux
mkdir -p ~/.claude/skills/
cp -r alibabacloud-adb-mysql-copilot ~/.claude/skills/
```

或创建符号链接（推荐开发环境使用）：

```bash
mkdir -p ~/.claude/skills/
ln -s "$(pwd)/alibabacloud-adb-mysql-copilot" ~/.claude/skills/alibabacloud-adb-mysql-copilot
```

### 3.5 验证安装

启动 Claude Code，调用技能：

```bash
claude
```

```bash
/alibabacloud-adb-mysql-copilot 我在杭州有多少 ADB MySQL 实例？
```

或直接验证脚本：

```bash
uv run ~/.claude/skills/alibabacloud-adb-mysql-copilot/scripts/call_adb_api.py \
    describe_db_clusters --region cn-hangzhou
```

## 四、使用示例

```bash
# 查询集群列表
uv run ./scripts/call_adb_api.py describe_db_clusters --region cn-hangzhou

# 查看集群详情
uv run ./scripts/call_adb_api.py describe_db_cluster_attribute --cluster-id amv-xxx

# 查询 CPU 性能（默认最近 1 小时）
uv run ./scripts/call_adb_api.py describe_db_cluster_performance \
    --cluster-id amv-xxx --key AnalyticDB_CPU

# 检测 Bad SQL
uv run ./scripts/call_adb_api.py describe_bad_sql_detection --cluster-id amv-xxx

# 查看运行中的 SQL
uv run ./scripts/call_adb_api.py describe_diagnosis_records --cluster-id amv-xxx \
    --query-condition '{"Type":"status","Value":"running"}'

# SQL Pattern 分析
uv run ./scripts/call_adb_api.py describe_sql_patterns --cluster-id amv-xxx

# 执行诊断 SQL（需配置 ADB_MYSQL_* 环境变量）
uv run ./scripts/call_adb_api.py execute_sql --query "SHOW PROCESSLIST"
```

## 五、常见问题

### 5.1 依赖缺失

如果出现 `ImportError`，手动安装依赖：

```bash
pip install alibabacloud-adb20211201 alibabacloud-tea-openapi alibabacloud-tea-util pymysql
```

### 5.2 凭证错误

确保环境变量 `ALIBABA_CLOUD_ACCESS_KEY_ID` 和 `ALIBABA_CLOUD_ACCESS_KEY_SECRET` 已正确设置：

```bash
echo $ALIBABA_CLOUD_ACCESS_KEY_ID   # 不应为空
echo $ALIBABA_CLOUD_ACCESS_KEY_SECRET  # 不应为空
```

### 5.3 Claude Code 无法识别技能

1. 确认技能已拷贝到 `~/.claude/skills/alibabacloud-adb-mysql-copilot/`
2. 确认 `SKILL.md` 文件存在于技能根目录
3. 重启 Claude Code
