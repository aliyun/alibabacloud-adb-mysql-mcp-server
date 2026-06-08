---
name: alibabacloud-adb-smart-analyst
description: ADB MySQL 语义层交互 skill。支持 AI Agent 通过 SQL（主方式）或 OpenAPI / aliyun CLI（语义方式）搜索语义视图、执行语义 SQL、管理语义视图 DDL，以及通过 Python 脚本探索物理表元数据。两种方式均需 ADB SQL 连接来执行最终查询。当用户提出针对 ADB MySQL 的数据分析问题时使用。
---

# ADB MySQL 智能分析师 Skill

## 使用时机

- 用户提出数据分析问题（如 "帮我看看销售数据"、"查一下北京的订单"、"最近一周的发货量"）
- 用户想创建、修改或删除语义视图
- 用户想探索数据库表结构或元数据
- 用户提到 ADB MySQL、AnalyticDB 或语义视图

## 前置条件

### ADB 连接（所有方式必须）

- **Python 3.6+**，并已安装 `pymysql` 包
- 安装依赖：`uv pip install pymysql`
- 可选依赖：`cryptography`（仅在以下场景需要，按需安装 `uv pip install cryptography`）：
  - 服务端使用 `caching_sha2_password`（MySQL 8.0 默认）或 `sha256_password` 鉴权插件
  - 连接走 TLS/SSL
  - 默认的 ADB MySQL Proxy 多采用 `mysql_native_password`，通常无需安装；若连接时报 `RuntimeError: 'cryptography' package is required ...`，再补装即可
- 必须设置以下环境变量（**无论使用哪种方式都需要**，因为最终 SQL 执行均通过 SQL 连接）：
  - `ADB_MYSQL_HOST` - ADB MySQL Proxy 主机地址
  - `ADB_MYSQL_PORT` - ADB MySQL Proxy 端口（默认：3306）
  - `ADB_MYSQL_DATABASE` - 默认数据库名
  - `ADB_MYSQL_USER` - 数据库用户名
  - `ADB_MYSQL_PASSWORD` - 数据库密码

### OpenAPI 方式附加条件（当语义层 SQL 方式不可用时）

> 当 SQL 方式的语义功能不可用（如缺少 `semantic_views` 元数据表、SQL hint 语义操作失败）时，语义操作切换到 OpenAPI 方式。数据查询执行仍通过上述 SQL 连接完成。

- **aliyun CLI** 已安装
- **adb CLI 插件**已安装
- **aliyun CLI 凭证**已由用户配置完成。可通过 `aliyun configure` 配置 AK/SK，但不建议 Agent 主动执行配置命令或代用户录入密钥；Agent 只做检测和使用。
- 必须设置：
  - `ADB_CLUSTER_ID` - ADB 集群 ID（必须，如 `am-bp1xxxxxxxx`）
  - `ADB_REGION` - 地域（可选，CLI profile 已含时可省略，如 `cn-hangzhou`）
- 凭证检测优先使用 `aliyun configure list` 或轻量级 OpenAPI 探测；不要仅依赖 `ALIBABA_CLOUD_*` 环境变量，因为默认 profile 也可提供有效凭证。
- RAM 权限要求（需为当前 AK/SK 对应的 RAM 用户或角色授权以下 Action）：
  - `adb:CreateSemanticView`
  - `adb:DeleteSemanticView`
  - `adb:ReplaceSemanticView`
  - `adb:GenerateSqlBySemanticSql`
  - `adb:RenameSemanticView`
  - `adb:SearchSemanticViews`
  - `adb:GetSemanticView`

## 架构

```
方式 A（主方式 - 全 SQL）：
  用户 → Agent → Skill → PyMySQL → ADB Proxy → MDS / ADB Engine

方式 B（OpenAPI 语义 + SQL 执行）：
  语义操作：用户 → Agent → Skill → aliyun CLI → OpenAPI Gateway → MDS
  数据执行：用户 → Agent → Skill → PyMySQL → ADB Proxy → ADB Engine
```

两种方式均通过 SQL 连接执行最终查询，区别仅在于语义操作的实现方式（SQL hint vs aliyun CLI）。Skill 优先 SQL 方式，SQL 语义功能不可用时自动切换 OpenAPI（详见下方「方式选择策略」）。

OpenAPI 方式下 `alter_semantic_view --operation set_comment` 不可用（计划补齐）。Skill 脚本自动添加 SQL hint，Agent 生成 SQL 时无需加 hint。

## 方式选择策略

Skill 采用 **SQL 优先 + 语义层自动切换** 策略，选择流程如下：

1. **检查 SQL 连接**：验证 ADB 连接环境变量（`ADB_MYSQL_HOST` 等）是否设置且连接可用
   - 连接失败（缺少环境变量、连接被拒、认证失败、超时）→ 报错提示检查 ADB 连接配置，**两种方式均不可用**
2. **尝试 SQL 方式语义功能**：SQL 连接可用后，尝试通过 SQL hint 执行语义操作
3. **SQL 语义功能正常** → 使用 SQL 方式（全功能）
4. **SQL 语义功能失败**（缺少 `semantic_views` 元数据表、SQL hint 语义操作报错）→ 检测 OpenAPI 方式前置条件：
   - `ADB_CLUSTER_ID` 环境变量存在？否 → 报错提示设置 `ADB_CLUSTER_ID`
   - CLI 环境完备性检查：
     - `aliyun` 可执行文件存在？（`which aliyun`）否 → 报错提示安装 aliyun CLI
     - `adb` 插件可用？（`aliyun adb --api-version 2021-12-01 --help`）否 → 报错提示安装 adb 插件（`aliyun plugin install --names adb`）
     - 凭证有效？（`aliyun configure list` 或一次轻量级探测调用验证）否 → 提示用户自行执行 `aliyun configure` 配置 AK/SK
   - 全部满足 → 切换到 OpenAPI 方式（语义操作通过 OpenAPI，数据执行和探索通过 SQL 连接）
5. **方式缓存**：方式选择结果在 Session 级别缓存，后续请求直接复用，不再重复检测。如需切换方式（如用户新配置了 SQL 语义层），需要新建 Session

## 两阶段问数流程

### 第一阶段 - 意图锚定（语义上下文感知）

1. 从用户问题中提取关键词
2. 调用 `search_semantic_views --top-k 3` 进行向量相似度搜索（top-k 固定为 3，不得调整）
3. 用户问题拆解：将自然语言问题拆解为「目标指标词」（用户想看什么数据）和「过滤条件词」（筛选条件）
4. 语义对象映射：逐个候选视图，从 YAML definition 中的 `name`、`description`、`synonyms`、`expr` 字段识别维度/指标/事实，判断用户的指标词和条件词能否映射
5. 决策：
   - **仅一个视图能完成映射**（或仅一个候选 score >= 0.5）：自决，输出映射表
   - **多个视图能映射且一个显著优于其他**（多覆盖 >= 2 个语义对象）：选最优，输出映射表
   - **多个视图映射覆盖度接近**：展示候选 + 各自映射关系，让用户选择
   - **没有视图能完成有意义的映射**：请用户澄清，展示最接近的候选及其部分覆盖
   - **所有候选 score < 0.5**：请用户进一步描述问题或补充关键词
   - **无结果**：请用户换个方式描述问题或提供更多上下文
6. **澄清-重检循环**：所有无法确定最终语义视图的情况（用户选择、澄清、补充关键词），用户回复后必须重新执行步骤 1-5（重新提取关键词 → 重新 `search_semantic_views` → 重新映射 → 重新决策），而非直接沿用之前的候选结果
7. **探索模式降级条件**（满足任一即降级）：
   - 经过 3 轮澄清-重检循环后仍无法确定语义视图
   - `search_semantic_views` 调用报错（如连接失败、语义服务不可用）
   降级时必须明确告知终止原因

**视图选择硬性规则：**
- 必须给出确定性推理：以「映射表」形式引用具体的语义对象 name/description/synonyms/expr，证明用户关键词与视图字段的对应关系
- 不得凭空捏造 YAML 定义中不存在的指标、维度或事实
- 不得在没有充分映射依据的情况下随意选择视图
- 不得在没有 `description` 或 `synonyms` 支持的情况下，将用户关键词与语义对象名强行建立同义关系
- 若同一用户关键词能合理映射到多个候选视图的不同语义对象，不得自决，必须展示候选让用户选择
- 若某个用户关键词无法基于 YAML 字段建立映射，必须标注为「未覆盖」
- 自决时映射表格式：`已选择视图 {schema}.{view_name}（score {x}）：「{关键词}」→ {对象类型} {name}`
- 候选展示时附带各视图的映射关系对比，帮助用户做出有区分度的选择

### 第二阶段 - 确定性执行

1. 基于所选视图的 YAML 定义生成语义 SQL
2. 通过 `execute_sql` 执行（默认 semantic_rewrite=true）
3. 展示结果，包括：数据表格、所用 SQL、分析结论、可视化建议、后续分析方向

**OpenAPI 方式下的第二阶段差异：**
- 使用 `generate-sql-by-semantic-sql` 命令进行语义 SQL 改写，获取改写后的物理 SQL
- 通过 `execute_sql --no-semantic-rewrite` 执行改写后的物理 SQL，获取查询结果
- 展示内容与 SQL 方式一致：数据表格、语义 SQL + 物理 SQL、分析结论、可视化建议、后续分析方向

## 降级策略 - 数据探索模式

当没有匹配的语义视图时，采用渐进式下钻探索：

### 四阶段探索流程

**第一阶段 - Schema 发现：**
```bash
uv run scripts/adb_analyst.py list_databases
```

**第二阶段 - 表发现与规模评估：**
```bash
uv run scripts/adb_analyst.py explore_table_metadata --operation list_tables --database logistics
uv run scripts/adb_analyst.py explore_table_metadata --operation table_statistics --database logistics --table shipments
```

**第三阶段 - 结构分析：**
```bash
uv run scripts/adb_analyst.py explore_table_metadata --operation describe_table --database logistics --table shipments
uv run scripts/adb_analyst.py explore_table_metadata --operation partition_info --database logistics --table shipments
uv run scripts/adb_analyst.py explore_table_metadata --operation show_create_table --database logistics --table shipments
uv run scripts/adb_analyst.py explore_table_metadata --operation index_info --database logistics --table shipments
```

**第四阶段 - 安全采样与查询：**
```bash
uv run scripts/adb_analyst.py explore_table_metadata --operation safe_sample --database logistics --table shipments --columns shipment_id,ship_date,status --limit 5
uv run scripts/adb_analyst.py explore_table_metadata --operation explain --database logistics --table shipments --sql "SELECT COUNT(*) FROM logistics.shipments WHERE ship_date >= '2026-05-01'"
uv run scripts/adb_analyst.py execute_sql --sql "SELECT destination_city, COUNT(*) AS cnt FROM \`logistics\`.\`shipments\` WHERE ship_date >= '2026-05-10' GROUP BY destination_city LIMIT 20" --no-semantic-rewrite
```

## 语义 SQL 规则

为已选视图生成语义 SQL 时须遵守以下规则：

| 规则 | 说明 | 示例 |
|------|------|------|
| 指标必须使用 `AGG()` | 由语义引擎映射聚合函数 | `AGG(order_count)` |
| SELECT 中的维度必须出现在 GROUP BY 中 | 一致性要求 | `SELECT city ... GROUP BY city` |
| WHERE 只能使用维度或事实字段 | 行级过滤 | `WHERE order_date >= '2025-01-01'` |
| HAVING 只能使用指标 | 聚合后过滤 | `HAVING AGG(order_count) > 100` |
| 必须包含 LIMIT | 防止结果集过大 | `LIMIT 100` |
| 字段名来自 YAML 的 `name` 字段 | 不得捏造字段名 | 使用 YAML 中 `name:` 的值 |
| 允许临时指标 | 对维度或事实字段使用聚合函数 | `COUNT(DISTINCT customer_name)` |

**语义 SQL 语法：**
```sql
SELECT [ DISTINCT ]
  {
    [<qualifiers>.]<dimension_or_fact> |
    AGG( [<qualifiers>.]<metric> ) |
    <aggregate_function>( [<qualifiers>.]<dimension_or_fact> )
  }
  [ , ... ]
FROM <semantic_view> [ AS <alias> ]
[ WHERE <expr_using_dimensions_or_facts> ]
[ GROUP BY <expr_using_dimensions_or_facts> [ , ... ] ]
[ HAVING <expr_using_metrics> ]
[ ORDER BY ... ]
LIMIT <n>
```

## 安全约束

- **禁止 DML**（INSERT/UPDATE/DELETE）
- **禁止 DROP DATABASE/TABLE**
- `execute_sql` 只接受 SELECT 语句
- DDL 操作（创建/修改/删除语义视图）需要用户明确指令
- 所有 SQL 参数使用参数化查询，防止注入攻击
- 探索模式：所有查询 LIMIT <= 100，并经过 SQL 白名单校验

## 防全表扫描规则（探索模式）

ADB MySQL 是分布式列式数据库，全表扫描代价极高。

| 规则 | 说明 |
|------|------|
| 查询数据前先查分区信息 | 任何数据查询前先调用 `partition_info` |
| 超大表（>1 亿行）必须添加时间过滤 | 先用 `table_statistics` 确认表规模 |
| 超宽表（>50 列）禁止 SELECT * | 使用列裁剪，只查所需字段 |
| 避免对非分布键的高基数列做 GROUP BY | 通过 `show_create_table` 查看 DISTRIBUTED BY 信息 |
| WHERE 中禁止对分区键使用函数 | `WHERE DATE_FORMAT(dt, '%Y-%m') = '2026-05'` 会破坏分区裁剪，应改用 `WHERE dt BETWEEN '2026-05-01' AND '2026-05-31'` |
| 聚合查询必须带分区过滤条件 | 无分区过滤 = 全表扫描 + shuffle |
| 大表执行前先 EXPLAIN | 使用 `explain` 操作检查执行计划 |
| 最多 2 层嵌套子查询 | 避免不可预期的性能问题 |

**按表规模确定默认时间范围：**

| 表规模（TABLE_ROWS 估算） | 默认时间范围 |
|--------------------------|-------------|
| < 100 万 | 不限制 |
| 100 万 ~ 1 亿 | 最近 1 个月 |
| > 1 亿 | 最近 7 天 |

## 工具调用示例

### SQL 方式工具调用示例

#### 搜索语义视图
```bash
uv run scripts/adb_analyst.py search_semantic_views --keywords "北京 销售" --top-k 3
```

#### 获取语义视图定义
```bash
uv run scripts/adb_analyst.py get_semantic_view --schema sales_db --view-name SALES_ANALYSIS
```

#### 执行 SQL（语义模式 - 默认）
```bash
uv run scripts/adb_analyst.py execute_sql --sql "SELECT city, AGG(revenue) FROM sales_db.SALES_ANALYSIS GROUP BY city LIMIT 100"
```

#### 执行 SQL（直连模式，用于探索）
```bash
uv run scripts/adb_analyst.py execute_sql --sql "SELECT * FROM sales_db.orders WHERE dt >= '2026-05-01' LIMIT 10" --no-semantic-rewrite
```

#### 创建语义视图
```bash
uv run scripts/adb_analyst.py create_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --yaml-file /tmp/view.yaml
```

#### 修改语义视图
```bash
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --operation rename --new-name SHIPPING_ANALYSIS
uv run scripts/adb_analyst.py alter_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS --operation set_comment --comment "Updated logistics view"
```

#### 删除语义视图
```bash
uv run scripts/adb_analyst.py drop_semantic_view --schema logistics --view-name LOGISTICS_ANALYSIS
```

#### 列出数据库
```bash
uv run scripts/adb_analyst.py list_databases
```

#### 探索表元数据
```bash
# 列出数据库中的所有表
uv run scripts/adb_analyst.py explore_table_metadata --operation list_tables --database logistics

# 查看表的列结构
uv run scripts/adb_analyst.py explore_table_metadata --operation describe_table --database logistics --table shipments

# 表统计信息（行数、数据量）
uv run scripts/adb_analyst.py explore_table_metadata --operation table_statistics --database logistics --table shipments

# 分区信息（分区键 + 各分区统计）
uv run scripts/adb_analyst.py explore_table_metadata --operation partition_info --database logistics --table shipments

# 安全采样（感知分区，自动检测分区键）
uv run scripts/adb_analyst.py explore_table_metadata --operation safe_sample --database logistics --table shipments --columns shipment_id,ship_date,status --limit 5

# 查看查询执行计划
uv run scripts/adb_analyst.py explore_table_metadata --operation explain --database logistics --table shipments --sql "SELECT COUNT(*) FROM logistics.shipments WHERE ship_date >= '2026-05-01'"

# 索引信息
uv run scripts/adb_analyst.py explore_table_metadata --operation index_info --database logistics --table shipments

# 查看建表 DDL
uv run scripts/adb_analyst.py explore_table_metadata --operation show_create_table --database logistics --table shipments
```

### OpenAPI 方式工具调用示例

#### 安装与使用约定

```bash
# 安装 aliyun CLI
/bin/bash -c "$(curl -fsSL https://aliyuncli.alicdn.com/install.sh)"

# 安装 adb CLI 插件
aliyun plugin install --names adb

# 用户本地配置 AK/SK（不建议 Agent 代用户执行或录入密钥）
aliyun configure
```

- Agent 使用 OpenAPI 方式前，只检测 `aliyun`、`adb` 插件、profile/凭证是否可用；凭证缺失或失效时提示用户自行配置。
- `adb` 产品默认 API 版本可能不是语义视图所在版本，所有语义 OpenAPI 命令均需显式指定 `--api-version 2021-12-01`。
- 所有语义 OpenAPI 命令均需指定 `--db-cluster-id`；跨地域或 profile 未设置地域时，额外指定 `--region`。
>
> **参数名称映射**（SQL 方式与 OpenAPI 方式参数名不同）：
> | SQL 方式（adb_analyst.py） | OpenAPI 方式（aliyun adb CLI） |
> |------------------------|----------------------|
> | `--keywords` | `--query-text` |
> | `--top-k` | `--topk` |
> | `--schema` | `--schema-name` |
> | `--view-name` | `--view-name` |
> | `--yaml-file` | `--definition` |

搜索（`search-semantic-views`）、获取（`get-semantic-view`）、创建（`create-semantic-view`）、删除（`delete-semantic-view`）的调用方式参照 SQL 方式示例，参数名按上表映射替换即可。以下仅列出 OpenAPI 独有命令：

#### 语义 SQL 改写（生成物理 SQL）
```bash
aliyun adb generate-sql-by-semantic-sql --api-version 2021-12-01 \
  --db-cluster-id am-bp1xxxxxxxx \
  --sql "SELECT city, AGG(revenue) FROM sales_db.SALES_ANALYSIS GROUP BY city LIMIT 100"
```

#### 替换语义视图
```bash
aliyun adb replace-semantic-view --api-version 2021-12-01 \
  --db-cluster-id am-bp1xxxxxxxx \
  --schema-name logistics \
  --view-name LOGISTICS_ANALYSIS \
  --definition "$(cat /tmp/view_v2.yaml)"
```

#### 重命名语义视图
```bash
aliyun adb rename-semantic-view --api-version 2021-12-01 \
  --db-cluster-id am-bp1xxxxxxxx \
  --old-schema-name logistics \
  --old-view-name LOGISTICS_ANALYSIS \
  --new-schema-name logistics \
  --new-view-name SHIPPING_ANALYSIS
```

## 结果展示规范

查询结果返回后，需展示以下 5 项（SQL 方式和 OpenAPI 方式通用）：

1. **数据表格**：以 Markdown 表格格式展示查询结果
2. **所用 SQL**：
   - **语义模式 / OpenAPI 模式**：必须同时展示语义 SQL + 真实执行 SQL（SQL 方式从 `rewrite_info.rewritten_sql` 提取；OpenAPI 方式从 `generate-sql-by-semantic-sql` 返回值提取）
   - **探索模式**（`--no-semantic-rewrite`）：只展示实际执行的 SQL
3. **文字分析**：关键发现、趋势、值得关注的规律
4. **可视化建议**：时间维度+指标→折线图；类别维度+指标→柱状图/饼图；两个维度+指标→热力图/分组柱状图
5. **后续分析方向**：建议更深入的分析路径

## 错误处理

| 错误场景 | Agent 行为 |
|----------|-----------|
| SQL 连接失败 | 告知用户两种方式均不可用，建议检查 ADB 连接环境变量和网络 |
| 语义搜索无结果 | 引导进入探索模式 |
| 搜索语义相关度极低（所有候选 score < 0.5） | 展示最接近的候选及其部分覆盖，请用户澄清或补充关键词；经 3 轮澄清仍无法确定则降级到探索模式 |
| 语义 SQL 语法错误 | 展示错误，自动修正重试（最多 2 次） |
| 语义引擎校验失败 | 重新读取 YAML 定义，修正 SQL |
| 查询超时 | 建议缩小时间范围或减少维度数量 |
| 权限不足 | 告知用户访问权限不够 |
| DDL 失败（向量化服务不可用） | 告知用户稍后重试，DDL 操作是原子性的 |
| aliyun CLI 未安装 | 提示安装 aliyun CLI |
| adb 插件缺失 | 提示安装 adb 插件（`aliyun plugin install --names adb`） |
| OpenAPI 凭证无效/过期 | 提示用户自行执行 `aliyun configure` 重新配置 |
| OpenAPI 权限不足 | 告知用户 RAM 权限不够，列出所需 Action |
| OpenAPI 语义改写失败但 SQL 连接可用 | 展示错误信息，建议用户检查语义 SQL 语法或视图定义 |

> **OpenAPI 重试策略**：网络超时或限流（`Throttling`）自动重试最多 3 次（指数退避 1s/2s/4s）；业务错误不重试。失败时记录 `RequestId` 便于排查。

## 端到端示例

### 正常路径：单视图自决

**用户**：帮我看看去年北京的销售情况

**第一步** - 提取关键词并搜索：
```bash
uv run scripts/adb_analyst.py search_semantic_views --keywords "北京 销售" --top-k 3
```

结果：SALES_ANALYSIS（score=0.91）、USER_PURCHASE（score=0.68）。

**第二步** - 问题拆解与语义对象映射：

问题拆解：
- 目标指标词：「销售情况」
- 过滤条件词：「北京」「去年」

SALES_ANALYSIS 视图映射验证：
- 「销售」→ metrics 中 `total_revenue`（description: "总销售收入"）、`order_count`（description: "订单数量"）✓
- 「北京」→ dimension `city`（description: "订单城市"）✓
- 「去年」→ dimension `order_year`（expr: `YEAR(order_date)`）✓

决策：SALES_ANALYSIS 完全覆盖所有关键词，且为唯一高分候选，自决。

**第三步** - 输出映射表并执行语义 SQL：

> 已选择视图 sales_db.SALES_ANALYSIS（score 0.91）：
>   「北京」→ 维度 city
>   「销售」→ 指标 total_revenue, order_count
>   「去年」→ 维度 order_year = 2025

```bash
uv run scripts/adb_analyst.py execute_sql --sql "SELECT city, order_year, AGG(total_revenue), AGG(order_count) FROM sales_db.SALES_ANALYSIS WHERE city = '北京' AND order_year = 2025 GROUP BY city, order_year LIMIT 100"
```

**第四步** - 展示结果：

> | 城市 | 年份 | 总收入 | 订单数 |
> |------|------|--------|--------|
> | 北京 | 2025 | 12,580,000.00 | 3,842 |
>
> **语义 SQL：**
> ```sql
> SELECT city, order_year, AGG(total_revenue), AGG(order_count)
> FROM sales_db.SALES_ANALYSIS
> WHERE city = '北京' AND order_year = 2025
> GROUP BY city, order_year LIMIT 100
> ```
>
> **真实执行 SQL：**
> ```sql
> SELECT o_city AS city, YEAR(o_orderdate) AS order_year,
>        SUM(o_revenue) AS total_revenue, COUNT(*) AS order_count
> FROM sales_db.orders
> WHERE o_city = '北京' AND YEAR(o_orderdate) = 2025
> GROUP BY o_city, YEAR(o_orderdate) LIMIT 100
> ```
>
> 分析：2025 年北京市场总收入 1258 万元，共 3842 笔订单，客单价约 3274 元。
>
> 建议进一步分析：月度趋势（折线图）、城市对比（柱状图）、客户群体贡献占比（饼图）。

### 歧义路径：多视图候选 → 澄清-重检循环

**用户**：帮我看看北京的发货情况

与正常路径的关键差异：
1. 搜索返回多个覆盖度接近的候选（如 SALES_ANALYSIS score=0.85、LOGISTICS_ANALYSIS score=0.83）
2. 两个视图均能完整映射「发货」和「北京」，但口径不同（销售口径 vs 物流口径）→ 展示候选 + 各自映射关系，让用户选择
3. 用户选择后触发**澄清-重检循环**（步骤 6）：将用户回复融入关键词重新搜索 → 重新映射 → 重新决策 → 确定视图后进入第二阶段

### 降级路径：澄清-重检后降级探索模式

**用户**：帮我看看库房利用率

与正常路径的关键差异：
1. 搜索返回结果全部 score < 0.5 → 请用户补充关键词或澄清含义
2. 经过 3 轮澄清-重检循环后仍无法匹配语义视图
3. 明确告知终止原因，降级进入「数据探索模式」四阶段探索流程

## 语义 YAML 规范摘要

语义视图通过 YAML 文件定义，结构如下：

```yaml
name: <view_name>
description: <string>
synonyms: [<string>, ...]

tables:
  - name: <logical_table_name>
    synonyms: [<string>, ...]
    base_table:
      schema: <physical_schema>
      table: <physical_table>
    dimensions:
      - name: <dim_name>
        description: <string>
        synonyms: [<string>, ...]
        expr: <SQL expression>
        data_type: <type>
    facts:
      - name: <fact_name>
        description: <string>
        synonyms: [<string>, ...]
        expr: <SQL expression>
        data_type: <type>
    metrics:
      - name: <metric_name>
        synonyms: [<string>, ...]
        description: <string>
        expr: <SQL aggregation expression>

relationships:
  - name: <rel_name>
    synonyms: [<string>, ...]
    left_table: <table>
    right_table: <table>
    relationship_columns:
      - left_column: <col>
        right_column: <col>

metrics:  # 视图级派生指标
  - name: <derived_metric_name>
    synonyms: [<string>, ...]
    expr: <expression referencing table-level metrics>
```

核心概念：Tables（逻辑表 -> 物理表映射）、Dimensions（谁/什么/在哪/何时）、Facts（行级度量值）、Metrics（通过 `AGG()` 聚合的度量）、Relationships（表关联关系）、Filters（命名过滤条件）、Verified Queries（示例问答对）。
