# ADB Smart Analyst - 快速启动指南

## 🚀 第一步：配置数据库连接

数据库连接信息通过**环境变量**管理，仅在当前 shell 会话中生效，不会写入文件。

首次使用时，直接告诉 AI：

> "帮我查询上月各渠道毛利"

AI 会自动检测环境变量是否已设置，如果未设置，会引导你在终端中执行：

```bash
export ADB_MYSQL_HOST=<您的数据库地址，如 amv-xxx.ads.aliyuncs.com>
export ADB_MYSQL_USER=<您的用户名>
export ADB_MYSQL_PASSWORD=<您的密码>
export ADB_MYSQL_PORT=3306
```

执行后告知 AI，即可继续执行原始请求。

> ⚠️ **安全说明**：环境变量仅在当前 shell 会话中有效，不会落盘或被提交到 Git。开启新终端时需重新执行上述命令。

---

## 📋 完整调用流程示例

### 场景：查询 1995 年亚洲地区销售额

```bash
# 定位 skill 目录
SKILL_DIR="$(find ~ -maxdepth 3 -name 'alibabacloud-adb-smart-analyst' -type d 2>/dev/null | grep -m1 alibabacloud-adb-smart-analyst)"

# Step 1: 语义检索 - 找到指标 YAML 定义
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py search_metrics_rag "revenue asia" --attempt 1
```

Step 1 返回 JSON，其中 `data[].definition` 是 YAML 字符串，**关键字段**：

| YAML 字段 | 含义 | 后续用途 |
|-----------|------|---------|
| `tables[].base_table` | 真正的**物理表**列表 | 传给 Step 2 校验 |
| `metrics` | 指标计算公式 | 写入 SQL SELECT |
| `dimensions` | 可用维度列 | 用于 GROUP BY / WHERE |
| `relationships` | 表间关联条件 | 用于 JOIN / WHERE |

```bash
# Step 2: 物理对齐 - 用 base_table 中的物理表，不是语义视图名！
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py get_batch_table_metadata \
  '[{"catalog":"adb_catalog","schema":"tpch","table":"lineitem"},{"schema":"tpch","table":"region"}]' \
  --attempt 1

# Step 3: SQL 执行
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql \
  "SELECT r.r_name AS region, SUM(l.l_extendedprice) AS revenue FROM adb_catalog.tpch.lineitem l JOIN tpch.region r ON l.l_regionkey = r.r_regionkey WHERE r.r_name = 'ASIA' GROUP BY r.r_name" \
  --attempt 1
```

---

## 🔧 命令参考

所有功能通过统一入口 `scripts/adb_smart_analyst.py` 调用。

### search_metrics_rag（Step 1 语义检索）

```bash
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py search_metrics_rag "keyword" [--top-k 5] --attempt N
```

| 参数 | 说明 |
|------|------|
| `query` | 业务关键词（英文），如 "revenue"、"profit margin"（位置参数） |
| `--top-k` | 返回条数，默认 5 |
| `--attempt` | 当前是第几次尝试（1-3），第 3 次触发全量兜底 |

---

### get_batch_table_metadata（Step 2 物理对齐）

```bash
# JSON 数组格式
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py get_batch_table_metadata \
  '[{"catalog":"c","schema":"db","table":"t1"},{"schema":"db","table":"t2"}]' \
  --attempt N
```

| 参数 | 说明 |
|------|------|
| `tables` | 必填，JSON 数组，支持 catalog(可选)/schema(必填)/table(必填) |
| `--attempt` | 当前是第几次尝试（1-3） |

---

### execute_adb_sql（Step 3 SQL 执行）

```bash
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py execute_adb_sql "SELECT ..." --attempt N
```

| 参数 | 说明 |
|------|------|
| `sql` | SQL 语句（位置参数） |
| `--attempt` | 当前是第几次尝试（1-3） |

---

### create_semantic_view（创建语义视图）

```bash
uv run --directory "$SKILL_DIR" scripts/adb_smart_analyst.py create_semantic_view "schema.view_name" "yaml_content"
```

---

## 🎯 如何触发 AI 自动调用 Skill

### 好的问法（AI 会调用此 Skill）
- "查询上月各渠道毛利率"
- "统计今年 GMV 同比增长"
- "各品类库存周转率排行"
- "分析华东区近 30 天订单量趋势"

### 不够精准的问法
- "帮我查个数据"（缺少指标词和维度词）
- "ADB 里有什么表？"（元数据探查，非问数需求）

---

## 📊 3x3 自愈机制

每个阶段最多 3 次，`--attempt N` 参数由 Agent 递增传入：

| 阶段 | attempt=1 | attempt=2 | attempt=3 | 超出上限 |
|------|-----------|-----------|-----------|---------|
| **Step 1** | 原始关键词 | 拆分/同义词 | 触发全量兜底 | 返回错误 |
| **Step 2** | 校验物理表字段 | 更换字段组合 | 回溯 Step 1 重检索 | 返回错误 |
| **Step 3** | 执行 SQL | 修正字段/语法 | 参考 YAML 重构 SQL | 返回错误 |

---

## 🔍 故障排查

### 数据库连接失败

```bash
# 检查环境变量是否已设置
echo "ADB_MYSQL_HOST=${ADB_MYSQL_HOST:-(not set)}"

# 重新设置环境变量
export ADB_MYSQL_HOST=<host>
export ADB_MYSQL_USER=<user>
export ADB_MYSQL_PASSWORD=<password>
export ADB_MYSQL_PORT=3306
```

### Step 1 搜索返回空结果

```sql
-- 直接查看库中有哪些语义视图
SELECT view_name, view_schema FROM information_schema.semantic_views LIMIT 20;
```

第 3 次调用时（`--attempt 3`）会自动触发**全量兜底**，返回所有语义视图记录。

### Step 2 找不到字段

确认传入的是 `base_table` 中的**物理表**，而非语义视图名：

```bash
# ✅ 正确：传物理表
'[{"catalog":"adb_catalog","schema":"tpch","table":"lineitem"}]'

# ❌ 错误：传语义视图名
'[{"table":"sales_view"}]'
```

---

## 📚 相关文档

- [SKILL.md](SKILL.md) - Skill 完整规范与工作流程
- [examples.md](examples.md) - 场景化调用示例
- [scripts/adb_smart_analyst.py](scripts/adb_smart_analyst.py) - 核心实现代码
