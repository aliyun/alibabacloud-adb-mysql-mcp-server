# ADB Smart Analyst - 快速启动指南

## 配置数据库连接

数据库连接信息通过**环境变量**管理，仅在当前 shell 会话中生效，不会写入文件。

首次使用时，直接告诉 AI：

> "帮我查询上月各渠道毛利"

AI 会自动检测环境变量是否已设置，如果未设置，会引导你在终端中执行：

```bash
export ADB_MYSQL_HOST=<ADB MySQL 集群地址，如 amv-xxx.ads.aliyuncs.com>
export ADB_MYSQL_PORT=3306
export ADB_MYSQL_DATABASE=<默认数据库名>
export ADB_MYSQL_USER=<用户名>
export ADB_MYSQL_PASSWORD=<密码>
```

执行后告知 AI，即可继续执行原始请求。

> **安全说明**：环境变量仅在当前 shell 会话中有效，不会落盘或被提交到 Git。开启新终端时需重新执行上述命令。

### 可选：OpenAPI 方式

当 SQL 方式的语义功能不可用时，Skill 自动切换到 OpenAPI 方式。需要额外配置：

- **aliyun CLI** 已安装，并安装 **adb** 插件
- **凭证** 已通过 `aliyun configure` 配置完成
- 环境变量：`ADB_CLUSTER_ID=<集群 ID，如 am-bp1xxxxxxxx>`
- 可选：`ADB_REGION=<地域，如 cn-hangzhou>`

数据执行仍通过 SQL 连接完成，OpenAPI 仅用于语义操作。

### 依赖安装

```bash
uv pip install pymysql
# 可选（仅在 caching_sha2_password 认证或 TLS 连接时需要）：
uv pip install cryptography
```

---

## 架构

```
方式 A（主方式 - 全 SQL）：
  用户 → Agent → Skill → PyMySQL → ADB Proxy → MDS / ADB Engine

方式 B（OpenAPI 语义 + SQL 执行）：
  语义操作：用户 → Agent → Skill → aliyun CLI → OpenAPI Gateway → MDS
  数据执行：用户 → Agent → Skill → PyMySQL → ADB Proxy → ADB Engine
```

Skill 优先使用 SQL 方式，SQL 语义功能不可用时自动切换到 OpenAPI 方式。

---

## 两阶段问数流程

### 第一阶段 — 意图锚定

1. 从用户问题中提取关键词
2. 调用 `search_semantic_views --keywords "关键词" --top-k 3` 搜索语义视图
3. 将用户问题拆解为「目标指标词」和「过滤条件词」
4. 逐个候选视图映射用户关键词到语义对象（维度、事实、指标）
5. 选择最佳匹配视图，或请用户澄清

### 第二阶段 — 确定性执行

1. 基于所选视图的 YAML 定义生成语义 SQL
2. 通过 `execute_sql` 执行（默认启用语义改写）
3. 展示：数据表格、语义 SQL + 改写后的真实 SQL、文字分析、可视化建议

---

## 完整调用流程示例

### 场景：查询 2025 年北京的销售额

```bash
# 第 1 步：搜索语义视图
uv run scripts/adb_analyst.py search_semantic_views --keywords "北京 销售" --top-k 3

# 第 2 步：执行语义 SQL（AGG() 包裹指标，引擎映射为实际聚合函数）
uv run scripts/adb_analyst.py execute_sql --sql "SELECT city, order_year, AGG(total_revenue), AGG(order_count) FROM sales_db.SALES_ANALYSIS WHERE city = '北京' AND order_year = 2025 GROUP BY city, order_year LIMIT 100"
```

---

## 命令参考

所有功能通过统一入口 `scripts/adb_analyst.py` 调用。

### search_semantic_views

通过关键词向量相似度搜索语义视图。

```bash
uv run scripts/adb_analyst.py search_semantic_views --keywords "销售 收入" --top-k 3
```

| 参数 | 说明 |
|------|------|
| `--keywords` | 空格分隔的搜索关键词（必填） |
| `--top-k` | 返回结果数量（默认: 3） |

### get_semantic_view

查询语义视图定义。

```bash
uv run scripts/adb_analyst.py get_semantic_view --schema sales_db --view-name SALES_ANALYSIS
```

| 参数 | 说明 |
|------|------|
| `--schema` | 按 schema 过滤 |
| `--view-name` | 按视图名称过滤（需配合 `--schema` 使用） |

### execute_sql

执行 SQL 查询，支持语义模式（默认）和直连模式。

```bash
# 语义模式（默认）— 自动添加语义改写 hint
uv run scripts/adb_analyst.py execute_sql --sql "SELECT city, AGG(revenue) FROM sales_db.VIEW GROUP BY city LIMIT 100"

# 直连模式 — 跳过语义改写，用于数据探索
uv run scripts/adb_analyst.py execute_sql --sql "SELECT * FROM sales_db.orders WHERE dt >= '2026-05-01' LIMIT 10" --no-semantic-rewrite
```

| 参数 | 说明 |
|------|------|
| `--sql` | SQL 语句（必填） |
| `--no-semantic-rewrite` | 跳过语义改写，使用直连模式 |
| `--max-rows` | 最大返回行数（默认: 500，直连模式上限 100） |

### create_semantic_view

```bash
uv run scripts/adb_analyst.py create_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --yaml-file /tmp/view.yaml
```

| 参数 | 说明 |
|------|------|
| `--schema` | 目标 schema（必填） |
| `--view-name` | 视图名称（必填） |
| `--yaml-file` | YAML 定义文件路径，使用 `-` 从标准输入读取（必填） |
| `--or-replace` | 附加 OR REPLACE 子句 |
| `--if-not-exists` | 附加 IF NOT EXISTS 子句 |

### alter_semantic_view

```bash
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name VIEW --operation rename --new-name NEW_VIEW
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name VIEW --operation set_comment --comment "更新后的视图"
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

探索物理表结构、统计信息和样本数据。

```bash
uv run scripts/adb_analyst.py explore_table_metadata --operation <操作> --database <数据库> [--table <表>] [选项]
```

| 操作 | 说明 | 需要 `--table` |
|------|------|---------------|
| `list_tables` | 列出数据库中的所有表 | 否 |
| `describe_table` | 查看表的列结构 | 是 |
| `table_statistics` | 行数和数据量 | 是 |
| `partition_info` | 分区键和分区统计 | 是 |
| `index_info` | 索引信息 | 是 |
| `show_create_table` | 查看建表 DDL | 是 |
| `safe_sample` | 感知分区的安全采样 | 是 |
| `explain` | 查看查询执行计划 | 是（+ `--sql`） |

---

## 如何触发 AI 自动调用 Skill

### 好的问法
- "查询上月各渠道毛利率"
- "统计今年 GMV 同比增长"
- "各品类库存周转率排行"
- "分析华东区近 30 天订单量趋势"
- "帮我创建一个物流分析的语义视图"
- "logistics 数据库里有什么表？"

### 降级到探索模式
当没有匹配的语义视图时，Skill 自动降级到探索模式，按四阶段流程执行：Schema 发现 → 表发现 → 结构分析 → 安全采样与查询。

---

## 故障排查

### 数据库连接失败

```bash
# 检查环境变量是否已设置
echo "ADB_MYSQL_HOST=${ADB_MYSQL_HOST:-(not set)}"
echo "ADB_MYSQL_USER=${ADB_MYSQL_USER:-(not set)}"

# 重新设置环境变量
export ADB_MYSQL_HOST=<host>
export ADB_MYSQL_PORT=3306
export ADB_MYSQL_DATABASE=<database>
export ADB_MYSQL_USER=<user>
export ADB_MYSQL_PASSWORD=<password>
```

### 语义搜索无结果

```bash
# 列出可用数据库
uv run scripts/adb_analyst.py list_databases

# 浏览某个 schema 下所有语义视图
uv run scripts/adb_analyst.py get_semantic_view --schema sales_db
```

经过 3 轮澄清仍无法确定语义视图时，Skill 降级到数据探索模式。

### 语义 SQL 报错

- 指标必须使用 `AGG()` 包裹：`AGG(total_revenue)`，而非 `SUM(total_revenue)`
- WHERE 只能使用维度或事实字段，不能使用指标
- HAVING 只能使用指标
- 字段名必须与 YAML 定义中的 `name` 一致
- 必须包含 `LIMIT`

---

## 相关文档

- [SKILL.md](SKILL.md) - Skill 完整规范与工作流程
- [examples.md](examples.md) - 场景化调用示例
- [scripts/adb_analyst.py](scripts/adb_analyst.py) - 核心实现代码
