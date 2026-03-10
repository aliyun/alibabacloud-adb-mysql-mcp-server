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
/alibabacloud-adb-mysql-copilot 我在张家口有几个实例
```

## 四、使用示例

以下示例中，将技能挂载后可直接在 Claude Code 对话中说出「你」中的内容，Claude 会按场景调用对应诊断并返回结果。

### 4.1 实例查找

查找指定区域下的实例列表。
```text
你：/alibabacloud-adb-mysql-copilot 查询杭州地域有哪些 ADBMySQL 实例？
Claude：[调用 ADBMySQL Copilot 并返回结果]
```

![cluster-info](../assets/cluster-info.jpg)

### 4.2 实例慢查询诊断

对指定实例执行指定时间的**慢查询诊断**。
```text
你：/alibabacloud-adb-mysql-copilot 针对张家口的实例amv-xxx，帮我做一下慢查询诊断，时间是最近2小时
Claude：[调用实例慢查询诊断逻辑，返回BadSQL和优化建议]
```

![cluster-info](../assets/slow-query-diagnosis.jpg)

### 4.3 实例空间诊断

对指定实例执行**完整空间巡检**（并行执行：过大非分区表、分区合理性、主键合理性、表数据倾斜、复制表合理性、空闲索引、冷热表共 7 项诊断），并汇总为一份健康巡检报告。

```text
你：/alibabacloud-adb-mysql-copilot 张家口集群，amv-xxx 实例空间诊断
Claude：[调用实例空间诊断逻辑，并行执行多项诊断并汇总返回实例健康巡检报告]
```

### 4.4 表数据倾斜诊断

检测实例下存在数据倾斜的事实表（易导致资源不均衡、长尾查询）。

```text
你：/alibabacloud-adb-mysql-copilot amv-xxx 这个实例有没有表数据倾斜？帮我查一下事实表倾斜情况
Claude：[调用表数据倾斜诊断逻辑，返回存在倾斜的事实表及倾斜情况]
```

### 4.5 分区合理性诊断

检测分区字段设计不合理的表（分区过大或过小会影响 Build 与查询性能）。

```text
你：/alibabacloud-adb-mysql-copilot amv-xxx 分区合理性诊断，看看有没有分区设计不合理的表
Claude：[调用分区合理性诊断逻辑，返回分区设计不合理的表及物理容量]
```

### 4.6 过大非分区表诊断

检测未分区且数据量过大的表（易触发全表 Build、磁盘与性能问题）。

```text
你：/alibabacloud-adb-mysql-copilot 查一下 amv-xxx 里有没有过大的非分区表
Claude：[调用过大非分区表诊断逻辑，返回异常表名、物理容量与行数]
```

### 4.7 复制表合理性诊断

检测行数过大的复制表（复制表采用广播写，行数过大会放大写入压力）。

```text
你：/alibabacloud-adb-mysql-copilot amv-xxx 复制表合理性诊断，有没有不合理的复制表
Claude：[调用复制表合理性诊断逻辑，返回不合理的复制表及容量、行数]
```

### 4.8 空闲索引优化建议

查看实例下可删除或优化的空闲/冗余索引建议。

```text
你：/alibabacloud-adb-mysql-copilot amv-xxx 有没有空闲索引优化建议？想省点存储和写入
Claude：[调用空闲索引优化建议逻辑，返回可优化索引及建议与预期收益]
```

### 4.9 冷热表优化建议

查看适合做冷热分层（热表转冷表）的优化建议，以降低成本。

```text
你：/alibabacloud-adb-mysql-copilot amv-xxx 冷热表优化建议，哪些表可以转冷存储
Claude：[调用冷热表优化建议逻辑，返回可转冷存储的表及建议与预期收益]
```

### 4.10 针对指定实例执行SQL

针对具体某个实例，可以配置这些环境变量`ADB_MYSQL_HOST/ADB_MYSQL_PORT/ADB_MYSQL_USER/ADB_MYSQL_PASSWORD/ADB_MYSQL_DATABASE`，来实现针对具体的实例执行SQL。

```text
你：/alibabacloud-adb-mysql-copilot amv-xxx 当前的冷热表转换进度怎么样了？
Claude：[调用系统表查询冷热表转换进度]

你：/alibabacloud-adb-mysql-copilot amv-xxx 常见的配置项的值
Claude：[调用系统表查询常见的配置项的值]
```
![cluster-info](../assets/sql-inspection.jpg)

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
