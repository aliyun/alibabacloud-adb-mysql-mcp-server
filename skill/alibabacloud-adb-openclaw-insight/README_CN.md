# ADB MySQL OpenClaw Insight - Claude Code Skill

实时采集 [OpenClaw](https://openclaw.io) 会话日志并推送至阿里云 [AnalyticDB MySQL（ADB MySQL）](https://www.alibabacloud.com/zh/product/analyticdb-for-mysql) 进行存储与深度分析。提供由 **SQL + Python + LLM** 驱动的三层洞察架构，帮助团队理解 AI 使用模式、控制成本并提炼组织智慧。

## 一、功能特性

- **L1 运营效率分析**：Token 效率分析、会话深度分布、工具链模式挖掘、高成本任务链归因、异常检测 —— 纯 SQL + Python 驱动，无需 LLM
- **L2 用户行为分析**：意图分类、任务复杂度评分、成功率估算、Prompt 质量评估、话题聚类、重试检测、思考深度分析、用户成熟度画像 —— 由 LLM 驱动
- **L3 组织认知分析**：技术栈热力图、知识盲区发现、最佳实践提炼、技能候选人发现、叙事报告生成 —— 由 LLM 驱动
- **实时日志采集**：持续采集 OpenClaw JSONL 会话文件和每日日志文件，通过文件偏移量检查点避免重复写入
- **定时采集**：与 OpenClaw Cron 集成，实现全自动增量数据采集
- **灵活分析窗口**：通过 CLI 对任意自定义时间范围执行分析
- **无 LLM 模式**：L1 分析完全不依赖 LLM 接口

## 二、环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip / pip3
- 可访问的阿里云 AnalyticDB MySQL 实例
- 已部署 OpenClaw 并正在生成会话文件（`~/.openclaw/agents/*/sessions/*.jsonl`）和日志文件（`/tmp/openclaw/openclaw-YYYY-MM-DD.log`）
- *（可选）* 用于 L2/L3 分析的 OpenAI 兼容或 Anthropic LLM API 接口

## 三、快速开始

### 3.1 克隆仓库

```bash
git clone https://github.com/aliyun/alibabacloud-adb-mysql-mcp-server
cd alibabacloud-adb-mysql-mcp-server/skill/alibabacloud-adb-openclaw-insight
```

### 3.2 安装 uv（推荐）

[uv](https://docs.astral.sh/uv/) 是一个快速的 Python 包管理器，可自动管理虚拟环境。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3.3 安装依赖

**使用 uv（推荐）：**

```bash
uv pip install -r requirements.txt
```

**使用 pip：**

```bash
pip install -r requirements.txt
# 如果找不到 "pip"，请尝试：
pip3 install -r requirements.txt
```

### 3.4 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`，填写 ADB 连接信息，以及（可选的）LLM API 配置。关键字段说明：

| 配置节 | 关键字段 | 说明 |
|--------|---------|------|
| `adb` | `host`, `port`, `database`, `username`, `password` | ADB MySQL 连接信息 |
| `collection` | `intervalMinutes`, `batchSize`, `retentionDays` | 采集行为配置 |
| `filters` | `minLevel`, `includeSubsystems`, `excludeSubsystems` | 日志过滤规则 |
| `llm` | `endpoint`, `apiKey`, `model` | L2/L3 分析所需的 LLM API 配置 |
| `analysis` | `enableL1`, `enableL2`, `enableL3`, `analysisWindowDays` | 分析开关 |

> **注意**：L1 分析无需 LLM。L2 和 L3 需要配置有效的 `llm.endpoint` 和 `llm.apiKey`。

### 3.5 初始化数据库

```bash
python -m scripts.init_db
# 如果找不到 "python"，请尝试：
python3 -m scripts.init_db
```

### 3.6 启动服务

```bash
python -m scripts.main
# 如果找不到 "python"，请尝试：
python3 -m scripts.main
```

## 四、CLI 命令

| 命令 | 用法 | 说明 |
|------|------|------|
| *（默认）* | `python -m scripts.main` | 启动服务：采集 + 定时分析 |
| `collect` | `python -m scripts.main collect` | 单次采集：采集所有新数据并保存文件偏移量后退出 |
| `analyze` | `python -m scripts.main analyze` | 执行完整分析（L1 → L2 → L3 → 最终报告） |
| `final-report` | `python -m scripts.main final-report` | 从数据库获取并打印最新的叙事报告 |

对自定义时间范围执行分析：

```bash
# 时间格式：YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
python -m scripts.analyze_usage --from "2026-03-01 00:00:00" --to "2026-03-10 23:59:59"
```

## 五、通过 OpenClaw Cron 定时采集

`python -m scripts.main collect` 是保持数据持续流入 ADB 的推荐方式。它执行单次采集后保存文件偏移量检查点并退出，可安全地被任意调度器反复调用。

将其注册为 OpenClaw Cron 任务（示例：每 5 分钟执行一次）：

```json
{
  "cron": "*/5 * * * *",
  "command": "python -m scripts.main collect",
  "cwd": "/path/to/alibabacloud-adb-openclaw-insight"
}
```

每次调用将：
1. 扫描自上次运行以来新增的 JSONL 会话文件和每日日志文件
2. 批量将新记录写入 ADB
3. 保存文件偏移量检查点（`.collect_state.json`），确保下次从断点继续
4. 干净退出 —— 无需管理后台进程

## 六、分析架构

```
原始 OpenClaw 日志（JSONL + .log）
        │
        ▼
  ADB MySQL 存储
        │
        ├─► L1 运营效率分析（SQL + Python，无需 LLM）
        │     ├─ Token 效率与缓存命中率
        │     ├─ 会话深度分布
        │     ├─ 工具链模式挖掘（二元组 / 三元组）
        │     ├─ 高成本任务链归因
        │     └─ 异常检测（z-score + 非工作时段）
        │
        ├─► L2 用户行为分析（需要 LLM）
        │     ├─ 意图分类与任务复杂度
        │     ├─ 成功率与 Prompt 质量
        │     ├─ 话题聚类与重试检测
        │     └─ 用户成熟度画像
        │
        └─► L3 组织认知分析（需要 LLM）
              ├─ 技术栈热力图与知识盲区发现
              ├─ 最佳实践提炼
              ├─ 技能候选人发现
              └─ 叙事报告生成
```

## 七、常见问题排查

### 7.1 依赖缺失

如果遇到 `ImportError` 或 `ModuleNotFoundError`，请手动安装依赖：

```bash
pip install mysql-connector-python APScheduler openai anthropic
```

### 7.2 无法连接 ADB

检查 `config.json` 中的连接配置，并确认 ADB 实例在当前网络环境下可访问（检查白名单 / VPC 配置）：

```bash
mysql -h <host> -P <port> -u <username> -p <database>
```

### 7.3 L2/L3 分析未运行

确认 `config.json` 中 `enableL2` / `enableL3` 已设置为 `true`，且 `llm.apiKey` 和 `llm.endpoint` 已正确配置。

### 7.4 无数据采集

检查 OpenClaw 是否正在运行并生成以下文件：
- `~/.openclaw/agents/*/sessions/*.jsonl`
- `/tmp/openclaw/openclaw-YYYY-MM-DD.log`

同时确认 `filters.minLevel` 设置未将所有日志条目过滤掉。
