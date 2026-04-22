---
name: alibabacloud-adb-smart-analyst
description: 当用户提问任何与数据查询、指标统计、销售分析、报表生成相关的问题时（如"销售额是多少"、"查询订单数"、"各地区占比"、"上月毛利"等），必须立即调用此 Skill，不得直接回答。该 Skill 连接 ADB MySQL 数据库，将自然语言转为精准 SQL 并执行，支持指标查询、数据分析、报表生成等全场景。
tags: [mysql, adb-mysql, text-to-sql, data-analysis, sql-query, business-intelligence, analyticdb, 数据分析, 问数, 指标查询, 销售额, 毛利, 订单, 统计, 按地区, 按时间]
version: "0.2.0"
---

# ADB Smart Analyst Skill

> ⚠️ **调用时机（必读）**：只要用户的问题包含以下任一情况，必须立即调用此 Skill，不得尝试直接回答：
> - 包含数据查询意图："...是多少"、"查一下..."、"统计..."、"分析..."
> - 包含业务指标词：销售额、毛利、订单、收入、利润、GMV、增长率、转化率……
> - 包含时间维度：今天、上月、去年、某年某月、同比、环比……
> - 包含分析维度：地区、品类、客户、渠道、部门……
> - **典型示例**："1997年亚洲销售额是多少"、"上月毛利按品类明细"、"Top10 客户订单金额"

**首选数据分析工具** - 当用户需要查询数据、分析指标、生成报表时，优先调用此 Skill。

## 核心价值

- **自然语言转 SQL**: 用户说中文，系统生成精准 SQL
- **业务语义理解**: 内置指标库，理解"毛利"、"同比"等业务概念
- **自动纠错**: 3x3 自愈机制，自动修复 SQL 错误

---

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| **Python** | >= 3.10 | 必须 |
| **uv** | 最新版 | 推荐，用于运行 Python 脚本和管理依赖 |

> 如果环境中没有 `uv`，可通过 `curl -LsSf https://astral.sh/uv/install.sh \| sh` 安装。

---

### 步骤 1：检查环境变量是否已存在

```bash
echo "ADB_MYSQL_HOST=${ADB_MYSQL_HOST:-(not set)}"
```

- 若输出有效地址（非 `not set`）→ **直接跳到问数流程，无需任何配置操作**
- 若输出 `not set` → 执行步骤 2

### 步骤 2：引导用户在当前 shell 中设置环境变量

当环境变量不存在时，**告知用户在终端执行 export 命令**（不写入任何文件）：

**Agent 回复用户**：

🔐 **配置数据库连接**

请在您当前的终端中执行以下命令（仅对本次会话生效，不会写入文件）：

```bash
export ADB_MYSQL_HOST=<您的数据库地址，如 amv-xxx.ads.aliyuncs.com>
export ADB_MYSQL_USER=<您的用户名>
export ADB_MYSQL_PASSWORD=<您的密码>
export ADB_MYSQL_PORT=3306
```

执行后告诉我，我将立即继续您的请求。

> ⚠️ **安全说明**：环境变量仅在当前 shell 会话中有效，不会落盘或被提交到 Git。下次开启新会话时需重新执行上述命令。

### 步骤 3：确认后立即继续执行原始请求

用户告知已设置后，**直接运行问数命令，无需额外操作**：

```bash
SKILL_DIR="$(find ~ -maxdepth 3 -name 'alibabacloud-adb-smart-analyst' -type d 2>/dev/null | grep -m1 alibabacloud-adb-smart-analyst)"
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py search_metrics_rag "用户原始问题中的关键词" --attempt 1
# 未找到时第2次重试：
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py search_metrics_rag "同义关键词" --attempt 2
```

若脚本报 `Incomplete database config` 错误，说明环境变量仍未生效，提示用户重新执行 export 命令。

### 连接信息说明

| 特性 | 说明 |
|-----|------|
| **无需重复设置** | 同一 shell 会话内，环境变量设置一次即可用于所有问数操作 |
| **新会话需重设** | 开启新终端或新会话时，需重新执行 export 命令 |
| **不落盘** | 账密信息仅存在于内存，不写入任何文件，不会被 Git 提交 |
| **密码不回显** | Agent 回复中永远不显示密码明文 |

---

## 触发条件（满足任一即调用）

### 1. 问句中包含数据查询意图
- "查一下..."、"帮我看看..."、"统计一下..."
- "...是多少"、"...有哪些"、"...怎么样"
- "给我..."、"告诉我..."、"列出..."

### 2. 问句中包含业务指标词
**财务类**: 收入、成本、利润、毛利、净利、费用、税、营收、营业额、销售额、GMV、流水
**比率类**: 利润率、毛利率、增长率、占比、渗透率、转化率、复购率、留存率、ROI、ARPU
**库存类**: 库存、库龄、周转率、积压、缺货、安全库存、入库、出库
**订单类**: 订单、退货、退款、取消、发货、签收、履约

### 3. 问句中包含时间维度词
**绝对时间**: 今天、昨天、本周、上周、本月、上月、本季度、今年、去年、2024年、Q1、Q2
**相对时间**: 最近7天、过去30天、近半年、YTD（年初至今）、MTD（月初至今）
**对比时间**: 同比、环比、同期、去年同期、上月同期

### 4. 问句中包含分析维度词
**地理**: 地区、省份、城市、区域、门店、仓库、网点
**组织**: 部门、团队、销售员、负责人、渠道、代理商
**产品**: 产品、品类、品牌、SKU、规格、型号
**客户**: 客户、会员、用户、VIP、新客、老客

### 5. 问句中包含分析操作词
**聚合**: 汇总、合计、总计、求和、统计、计算
**排序**: 排行、排名、Top、前N、最高、最低、最大、最小
**对比**: 对比、比较、差异、变化、增减、涨跌
**分布**: 分布、占比、结构、构成、细分
**趋势**: 趋势、走势、变化、波动、增长、下降

---

## ⚠️ 场景区分（重要）

根据用户意图，区分两种完全不同的处理流程：

### 场景 A：问数 / NL2SQL（走 Step 1 → Step 2 → Step 3 流程）

**触发特征**：用户用**自然语言描述业务问题**，需要查询数据结果。

| 典型问法 | 分析意图 |
|---------|--------|
| "上月销售额是多少" | 查询业务指标数值 |
| "各地区的毛利排名" | 数据分析 + 排序 |
| "今年和去年收入对比" | 同比分析 |
| "Top10 客户订单金额" | 排名分析 |
| "退货率趋势" | 趋势分析 |

**处理流程**：Step 1（语义检索）→ Step 2（元数据校验）→ Step 3（SQL 执行）→ 展示结果

### 场景 B：查询语义视图（直接执行 SQL）

**触发特征**（满足任一即触发）：
1. 问题中包含 **"语义视图"**、**"semantic view"**、**"view"** 关键词
2. 问题中包含 **具体的视图名**（如 `schema.view_name` 格式）
3. 动词为 **"查看"、"详情"、"内容"、"定义"** 且对象是视图或元数据
4. 用户要查看的是 **视图定义本身**，而非业务数据

| 典型问法 | 分析意图 |
|---------|--------|
| "查看有哪些语义视图" | 列出所有语义视图 |
| "查询 test.tpch_chain_view 语义视图的详情" | 查看特定视图定义 |
| "tpch_sales_view 的内容是什么" | 查看视图定义 |
| "语义视图里有哪些表" | 查看视图元数据 |
| "搜索包含 xxx 的语义视图" | 模糊搜索视图定义 |
| "查看 xxx_view 的定义" | 查看特定视图 |

**处理流程**：直接生成 SQL 查询 `information_schema.semantic_views` → `execute_adb_sql` → 展示结果

> ⚠️ **注意**：场景 B **不经过** Step 1/2/3 流程，直接查询语义视图元数据表。

---

## 工具函数说明

### search_metrics_rag(query)
**用途**: 根据业务关键词查找指标定义（YAML 格式）

**参数**:
- `query` (str, 必填, 必须使用英文): 业务关键词，如 "revenue"、"profit margin"

**返回**: 包含指标计算公式、依赖表、验证 SQL 的 YAML 定义

**调用时机**: 用户提到业务指标时首先调用

---

### get_batch_table_metadata(tables)
**用途**: 查询物理表的字段结构

**参数**:
- `tables` (list, 必填): 表名列表
  - 格式: `[{"schema": "db_name", "table": "table_name"}]`
  - 简化: `[{"table": "table_name"}]`

**返回**: 表的列名、类型、注释信息

**调用时机**: 获取到 YAML 定义后，校验字段是否存在

---

### execute_adb_sql(sql)
**用途**: 执行 SQL 查询并返回结果

**参数**:
- `sql` (str, 必填): 要执行的 SQL 语句

**返回**: 查询结果集或原生错误信息

**调用时机**: 生成 SQL 后执行查询

**表名引用规则**： ADB MySQL 支持 `catalog.schema.table` 三层结构
- YAML `base_tables` 中有 `catalog` 字段时，**SQL 必须使用 `catalog.schema.table` 全限定名**
- 无 `catalog` 时使用 `schema.table`
- 不得将 catalog 丢弃，否则 ADB 无法路由到对应的外部表

---

### create_semantic_view(name, yaml_content)
**用途**: 创建语义视图

**参数**:
- `name` (str, 必填): 语义视图名称，格式为 `[schema.]view_name`
- `yaml_content` (str, 必填): YAML 定义内容
- `or_replace` (bool, 默认 True): 是否使用 OR REPLACE
- `if_not_exists` (bool, 默认 True): 是否使用 IF NOT EXISTS

**返回**: {status:success/error, message:..., name:...}

**调用示例**:
```bash
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py create_semantic_view "tpch.tpch_sales" "name: tpch_sales\ntables:\n  ..."
```

---

### DROP / ALTER SEMANTIC VIEW（通过 execute_adb_sql 执行）

以下操作不提供单独的封装方法，由 Agent 根据语法生成 SQL 后调用 `execute_adb_sql` 执行。

#### DROP SEMANTIC VIEW 语法

```sql
DROP SEMANTIC VIEW [ IF EXISTS ] [view_schema.]view_name
```

**示例**:
```sql
DROP SEMANTIC VIEW tpch.tpch_sales
DROP SEMANTIC VIEW IF EXISTS tpch_sales
```

#### ALTER SEMANTIC VIEW 语法

```sql
ALTER SEMANTIC VIEW [ IF EXISTS ] [view_schema.]view_name RENAME TO [view_schema.]new_view_name
```

**示例**:
```sql
ALTER SEMANTIC VIEW tpch.old_view RENAME TO tpch.new_view
ALTER SEMANTIC VIEW IF EXISTS old_view RENAME TO new_view
```

**调用方式**：Agent 生成上述 SQL 后，调用 `execute_adb_sql(sql)` 执行。

---

### 查询语义视图（通过 execute_adb_sql 执行）

当用户需要查看语义视图内容时，通过查询 `information_schema.semantic_views` 表实现。Agent 根据需求生成 SQL。

#### 查看所有语义视图

```sql
SELECT view_schema, view_name, definition
FROM information_schema.semantic_views
ORDER BY view_schema, view_name
```

#### 按名称查询特定语义视图

```sql
SELECT view_schema, view_name, definition
FROM information_schema.semantic_views
WHERE view_name = 'view_name'
-- 或使用 schema 过滤：
-- WHERE view_schema = 'schema_name' AND view_name = 'view_name'
```

#### 模糊搜索语义视图

```sql
SELECT view_schema, view_name, definition
FROM information_schema.semantic_views
WHERE view_name LIKE '%keyword%'
   OR definition LIKE '%keyword%'
```

**调用方式**：Agent 根据用户需求生成上述 SQL，调用 `execute_adb_sql(sql)` 执行并展示结果。

---

# 语义层 YAML 解读与使用规则

### ⚠️ 核心认知：语义视图不是物理表

`search_metrics_rag` 返回的是**逻辑定义**，不是可以直接查询的物理表。

| 概念 | 正确理解 | 错误做法 |
|------|----------|-----------|
| 语义视图名 (YAML `name`) | 语义层的逻辑名，存在于 `information_schema.semantic_views` 中 | ❌ `DESCRIBE view_name` / `SELECT * FROM view_name` |
| `tables[].base_table` | 每张语义表对应的真实物理表，Step 2/Step 3 使用此字段 | ✅ 提取全部 base_table 去 Step 2 校验 |
| `tables[].metrics[].expr` | 指标的计算表达式，直接写入 SQL SELECT | ✅ 直接用于 SQL 生成 |
| `tables[].dimensions[].expr` | 维度列表达式，用于 GROUP BY / WHERE | ✅ 直接用于 SQL 生成 |
| `tables[].time_dimensions[].expr` | 时间维度表达式，用于 WHERE 时间过滤 | ✅ 直接用于 SQL 生成 |
| `relationships` | 表间 JOIN 关联定义，包含左右表与 JOIN 列 | ✅ 直接用于构建 JOIN 路径 |

---

### YAML 返回结构示例（JSON字段名也一样）

```yaml
name: tpch_sales_analytics              # 语义视图名，仅作标识
description: 销售额与市场表现综合分析视图

tables:
  - name: lineitem                      # 语义表别名（用于 JOIN 关联）
    description: 订单行项与价格信息
    base_table:                         # ← 真实物理表，Step 2 传参来源！
      catalog: adb_catalog              # 可选；null/缺省表示 ADB 内部表
      schema: tpch_10g
      table: lineitem
    dimensions:
      - name: line_number
        expr: l_linenumber              # ← 维度列表达式，用于 GROUP BY/WHERE
        data_type: integer
    facts:
      - name: extended_price
        expr: l_extendedprice
    metrics:                            # ← 指标计算公式，直接写入 SQL SELECT
      - name: revenue
        synonyms: ["\u9500\u552e\u989d", "\u6536\u5165"]
        description: 折后总金额
        expr: SUM(l_extendedprice * (1 - l_discount))
      - name: avg_discount_rate
        synonyms: ["\u5e73\u5747\u6298\u6263\u7387"]
        expr: AVG(l_discount)

  - name: orders
    base_table:
      catalog: adb_catalog
      schema: tpch_10g
      table: orders
    time_dimensions:                    # ← 时间维度，用于 WHERE 时间过滤
      - name: order_date
        synonyms: ["\u8ba2\u5355\u65e5\u671f"]
        expr: o_orderdate
    dimensions:
      - name: order_priority
        expr: o_orderpriority

  - name: region
    base_table:
      schema: tpch                 # 无 catalog：属于 ADB 内部表
      table: region
    dimensions:
      - name: region_name
        synonyms: ["\u5730\u533a", "\u4e9a\u6d32", "\u6b27\u6d32"]
        expr: r_name

relationships:                        # ← 表间 JOIN 关联定义
  - name: rel_lineitem_orders
    left_table: lineitem
    right_table: orders
    relationship_columns:
      - left_column: l_orderkey
        right_column: o_orderkey
  - name: rel_nation_region
    left_table: nation
    right_table: region
    relationship_columns:
      - left_column: n_regionkey
        right_column: r_regionkey
```

---

### YAML → SQL 的正确转化步骤

**第一步：从 YAML 提取物理表列表（用于 Step 2）**

遍历所有 `tables[].base_table`，将其中的 `catalog`/`schema`/`table` 原样映射为 Step 2 传参：

```
tables:
  - name: lineitem
    base_table: {catalog: adb_catalog, schema: tpch_10g, table: lineitem}   # 有 catalog
  - name: region
    base_table: {schema: tpch, table: region}                           # 无 catalog

→ 传给 get_batch_table_metadata：
  [
    {"catalog": "adb_catalog", "schema": "tpch_10g", "table": "lineitem"},
    {"schema": "tpch", "table": "region"}
  ]
```

> ⚠️ **catalog 填写规则**：
> - `catalog` 必须取自 YAML `tables[].base_table.catalog`，**不得自行猜测或修改**
> - YAML 中无 `catalog` 字段时，不传 `catalog` 字段
> - `schema` 必填，不得缺省
> - 当 catalog 不为空且不是 `"adb"` 时，工具自动通过 `DESC catalog.schema.table` 查询

**第二步：用 YAML `metrics[].expr` 构建 SELECT 子句**

```
tables.lineitem.metrics:
  - name: revenue,  expr: SUM(l_extendedprice * (1 - l_discount))

用户问销售额 → 匹配 synonyms ["\u9500\u552e\u989d"] →
  SELECT SUM(l_extendedprice * (1 - l_discount)) AS revenue
```

**第三步：用 YAML `dimensions[].expr` 构建 GROUP BY（根据用户问题选择）**

```
用户问"按地区统计" → 匹配 tables.region.dimensions[region_name].synonyms ["\u5730\u533a"]
  对应物理列 r_name → GROUP BY r.r_name
```

**第四步：用 YAML `time_dimensions[].expr` 构建时间过滤**

```
用户问"1997年" → 匹配 tables.orders.time_dimensions[order_date]
  对应物理列 o_orderdate → WHERE YEAR(o.o_orderdate) = 1997
```

**第五步：用 YAML `relationships` 构建 JOIN 路径**

```
涉及表：lineitem, orders, region
→ 根据 relationships 找 JOIN 路径：
   lineitem --[l_orderkey=o_orderkey]--> orders --[...]--> nation --[n_regionkey=r_regionkey]--> region
```

**第六步：组合成完整 SQL（表名使用 `base_table` 中的物理表名）**

> ⚠️ **表名引用规则**：
> - `tables[].base_table` 中有 `catalog` 时，SQL 必须使用 `catalog.schema.table` 三层全限定名
> - 无 `catalog` 时使用 `schema.table` 两层即可
> - **不得忽略 catalog**，否则 ADB 无法路由到对应的外部表

```sql
-- YAML 里 lineitem/orders/customer/nation 的 base_table.catalog = adb_catalog
-- YAML 里 region 的 base_table 无 catalog
SELECT
  r.r_name                                       AS region_name,
  SUM(l.l_extendedprice * (1 - l.l_discount))   AS revenue
FROM adb_catalog.tpch_10g.lineitem l             -- 有 catalog → 三层全限定
JOIN adb_catalog.tpch_10g.orders    o  ON l.l_orderkey  = o.o_orderkey
JOIN adb_catalog.tpch_10g.customer  c  ON o.o_custkey   = c.c_custkey
JOIN adb_catalog.tpch_10g.nation    n  ON c.c_nationkey = n.n_nationkey
JOIN tpch.region                r  ON n.n_regionkey = r.r_regionkey  -- 无 catalog → 两层
WHERE r.r_name = 'ASIA'
  AND YEAR(o.o_orderdate) = 1997
GROUP BY r.r_name
ORDER BY revenue DESC
```

---

### Step 2 校验的正确目标

Step 2 的目的是**验证 YAML 中列出的物理表字段确实存在**，不是验证语义视图名。

```
# YAML tables[].base_table 示例：
tables:
  - name: lineitem
    base_table: {catalog: adb_catalog, schema: tpch_10g, table: lineitem}   # 有 catalog
  - name: region
    base_table: {schema: t'p'ch, table: region}                           # 无 catalog

# 正确传参（严格映射 base_table 字段）：
[
  {"catalog": "adb_catalog", "schema": "tpch_10g", "table": "lineitem"},
  {"schema": "tpch", "table": "region"}
]
```

- ✅ 正确：`catalog`/`schema`/`table` 均来自 `tables[].base_table`，直接映射，不修改
- ❌ 错误：传入语义视图名 `get_batch_table_metadata([{"table": "tpch_sales_analytics"}])`
- ❌ 错误：传入语义表别名 `get_batch_table_metadata([{"table": "lineitem"}])`（`lineitem` 是 YAML 语义表名，物理表名应取自 `base_table.table`）
- ❌ 错误：缺少 schema `get_batch_table_metadata([{"catalog": "adb_catalog", "table": "lineitem"}])`
- ❌ 错误：自行生造 catalog 字段（必须取自 YAML）

如果 Step 2 返回的实际列名与 YAML 中的 expr 不一致，需回溯 Step 1 重新检索。

---

## 标准工作流程

```
用户问数请求（如"查询上月毛利"）
    ↓
[检查] 环境变量 ADB_MYSQL_HOST 是否已设置？
    ↓ 未设置 → 引导用户在当前 shell 中执行 export 命令
    ↓           → 用户执行后告知我，立即继续执行原始请求
    ↓ 已设置 → 直接继续（无需任何配置操作）
    ↓
[Step 1] search_metrics_rag --attempt N → 获取指标定义 YAML
    ↓ 未找到 → 将 --attempt 加1 后重试（最多 3 次）
    ↓           → --attempt 1: 原始关键词
    ↓           → --attempt 2: 拆分关键词（如“毛利”→“利润”）
    ↓           → --attempt 3: 同义词或宽泛词，同时触发全量兜底
    ↓           → 3 次都失败 → 返回错误，不继续执行
    ↓ 找到 → 解析 YAML：
    ↓           → 提取 tables[].base_table 列表（物理表 + catalog/schema/table）
    ↓           → 记录每张表的 catalog 字段（有则必须保留至 SQL）
    ↓           → 记录 metrics[].expr 计算公式（用于生成 SQL SELECT）
    ↓           → 记录 dimensions[]/time_dimensions[] 维度（用于 GROUP BY/WHERE）
    ↓           → 记录 relationships JOIN 关联定义
    ↓           → 《必须继续执行 Step 2》不得跳过！
    ↓
[Step 2] get_batch_table_metadata(base_tables) --attempt N → 校验物理表字段
    ↓ 字段不存在 → 回溯 Step 1 重新检索（最多 3 次）
    ↓ 找到 → 继续（字段存在，可信水平）
    ↓
[生成 SQL 自检] 写 SQL 前必须逐表确认：
    ↓  该表在 YAML base_table 里有 catalog 字段？
    ↓    是 → SQL 中必须写 catalog.schema.table （三层全限定）
    ↓    否 → SQL 中写 schema.table （两层）
    ↓  不得将 catalog 省略，否则 ADB 无法路由到外部表
    ↓
生成 SQL（YAML 公式 + Step 2 实际字段 + 用户条件 + **正确表名引用格式**）
    ↓
[Step 3] execute_adb_sql --attempt N → 执行并返回结果
    ↓ 报错 → 将 --attempt 加1 后重试，最多 3 次
    ↓ 成功 → 展示结果
```

### 📋 结果展示规范

**重要**：向用户展示查询结果时，必须同时展示执行的 SQL 语句，格式如下：

```
📊 查询结果

执行 SQL：
```sql
SELECT ... FROM ... WHERE ...
```

| 列名1 | 列名2 | 列名3 |
|-------|-------|-------|
| 值1   | 值2   | 值3   |
| ...   | ...   | ...   |

共 N 条记录
```

**目的**：
- 让用户清楚知道执行了什么 SQL
- 方便用户验证结果是否符合预期
- 提高透明度和可追溯性

**核心要点**：
- 环境变量已存在时无需任何配置，同一 shell 会话内多次问数不重复设置
- 环境变量不存在时，引导用户在当前 shell 中 export，不写入任何文件
- 密码不在对话中回显
- **SQL 表名必须包含 catalog**：YAML `base_table` 有 catalog 字段时，表名必写为 `catalog.schema.table`，不得省略 catalog
- **结果展示必须包含 SQL**：向用户展示查询结果时，必须同时展示执行的 SQL 语句

---

## Step 2 强制要求（必须遵守）

**重要**: 每次拿到 Step 1 返回的 YAML 后，**必须执行 Step 2**，无论 YAML 内容多么详尽！

### 禁止行为

- **禁止**: Step 1 成功后直接跳过 Step 2 生成 SQL
- **禁止**: 以“YAML 已有字段信息”为由省略 Step 2
- **禁止**: 以“已知道表结构”为由省略 Step 2
- **必须**: Step 1 找到 YAML 后，立即调用 `get_batch_table_metadata`

### 为什么 YAML 中已有字段信息也必须进行 Step 2？

YAML 是语义层的逻辑定义，可能与数据库实际状态不同步：

| 场景 | 后果 |
|------|------|
| 表被重命名或字段被改名 | SQL 執行报 `Unknown column` |
| YAML 字段拼写误差 | SQL 生成错误字段名 |
| 表已迁移到其他 schema | SQL 报 `Table not found` |

Step 2 是以实际数据库字段为准，不是以 YAML 为准。**SQL 必须基于 Step 2 返回的字段生成。**

### 正确流程

```
Step 1 返回 YAML（含 measures/base_tables/dimensions）
    ↓ 不论 YAML 多么详尽都必须执行 Step 2 ↓
Step 2: get_batch_table_metadata(base_tables) → 得到真实字段列表
    ↓
用 Step 2 实际字段 + YAML 表达式 生成 SQL
    ↓
Step 3: execute_adb_sql
```

---

## Step 1 重试规则（必须遵守）

**重要**: 当 `search_metrics_rag` 返回空结果时，**必须重试**，不能跳过！

### 重试策略

| 重试次数 | 策略 | 示例 |
|---------|------|------|
| 第 1 次 | 原始关键词 | `search_metrics_rag(query="毛利")` |
| 第 2 次 | 拆分关键词 | `search_metrics_rag(query="利润")` |
| 第 3 次 | 使用同义词 | `search_metrics_rag(query="收益")` |
| 第 4 次 | 更宽泛的词 | `search_metrics_rag(query="财务")` |

### 禁止行为

- **禁止**: Step 1 未找到结果后直接构建 SQL
- **禁止**: Step 1 未找到结果后跳过 Step 1 继续执行
- **必须**: Step 1 未找到结果后，更换关键词重试，最多 3 次

### 正确流程

```
search_metrics_rag("销售额") → 未找到
    ↓
更换关键词：search_metrics_rag("销售") → 未找到
    ↓
更换关键词：search_metrics_rag("营收") → 未找到
    ↓
3 次都失败 → 告知用户“指标库中未找到相关定义”，停止执行
```
