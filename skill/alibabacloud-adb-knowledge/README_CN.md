# ADB Knowledge 客户使用指南

[English](README.md) | 中文

这个 skill 直接使用阿里云 CLI 完成以下操作，不提供额外包装脚本：

1. 将本地或 NAS 文件上传到 OSS。
2. 将一个 OSS 文件或整个 OSS 目录加入 ADB 知识库。
3. 使用自然语言问题调用 ADB 知识库召回。

## End-to-end workflow

涉及上传或入库的任务必须严格按以下四步顺序执行：

1. **环境检查** — 验证 CLI、ADB 插件和必要参数可用（参见第 1–4 节）。
2. **Bucket 选择** — 执行 `list-lake-storages`，提取 `Items[].LakeStorageId`，将这些 Bucket 名称展示给用户并让用户选择一个。此步骤是独立的前置条件，不可跳过或假设已有 Bucket。
3. **上传 + 入库** — 上传文件到 OSS → `aliyun oss stat` 验证 → 立即执行 `add-knowledge-file`。三步是一个原子序列，不需要等待用户额外下达入库指令。
4. **召回** — `get-knowledge-recall`，完整原样输出结果。

**步骤 2（Bucket 选择）是独立的前置步骤，必须在任何上传或入库操作之前完成。**

## 1. 安装阿里云 CLI

要求阿里云 CLI 3.x。

### macOS

```bash
brew install aliyun-cli
```

### Linux

```bash
/bin/bash -c "$(curl -fsSL https://aliyuncli.alicdn.com/install.sh)"
```

### Windows

1. 下载 `https://aliyuncli.alicdn.com/aliyun-cli-windows-latest-amd64.zip`。
2. 解压 `aliyun.exe` 到固定目录。
3. 将该目录加入系统 `Path`。
4. 重新打开终端。

验证或升级：

```bash
aliyun version
aliyun upgrade --yes
```

## 2. 配置凭证

交互配置：

```bash
aliyun configure
```

也可以使用阿里云 CLI 凭证环境变量：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="<access-key-id>"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="<access-key-secret>"
export ALIBABA_CLOUD_SECURITY_TOKEN="<sts-token>"  # 仅 STS 需要
```

生产环境优先使用 RAM 角色或临时凭证。不要把 AccessKey Secret 提交到仓库。

当前身份需要具备 OSS 目标路径读写权限，以及 ADB 知识文件入库和知识召回权限。

## 3. 安装 ADB 插件

从公开插件源安装：

```bash
aliyun plugin install --name aliyun-cli-adb
```

已经安装时可以更新：

```bash
aliyun plugin update --name aliyun-cli-adb
```

## 4. 检查安装

```bash
aliyun version
aliyun plugin show --name aliyun-cli-adb
aliyun adb list-lake-storages --api-version 2021-12-01 --help
aliyun adb add-knowledge-file --api-version 2021-12-01 --help
aliyun adb get-knowledge-recall --api-version 2021-12-01 --help
```

确认：

- `list-lake-storages` 包含 `--biz-region-id`、`--page-number` 和 `--page-size`。
- `add-knowledge-file` 包含 `--is-dir` 和 `--upload-user`。
- `get-knowledge-recall` 可用，并支持 `--topk`。
- CLI 接受全局参数 `--read-timeout`。

## 5. 设置常用环境变量

```bash
export ADB_INSTANCE_ID="amv-xxxxxxxxxxxxxx"
```

湖存储 Bucket 查询所需的 `--biz-region-id` 无需单独设置，skill 会自动使用 aliyun CLI 当前 profile 的默认 Region。

如果客户环境要求显式指定标准地域，再设置：

```bash
export ADB_REGION="<region-id>"
```

`ADB_REGION` 是选填项。仅在变量有值时，才在入库或召回命令中添加 `--region`；未设置时应完整省略该参数。客户版命令不添加 `--endpoint`。

`OSS_BUCKET` 只能配置为 `list-lake-storages` 返回的 `Items[].LakeStorageId`，不支持自定义 Bucket 名称。若已配置则直接使用；若未配置，按下一节查询并选择。

## 6. 选择湖存储 Bucket

上传文件或上报入库信息前，必须先解析 `OSS_BUCKET`：

1. 检查 `OSS_BUCKET` 是否已有值；有值时将其作为预先选择的湖存储 Bucket 使用。
2. 没有值时，通过 `aliyun configure get region` 自动读取当前 profile 的默认 Region。该命令只返回 Region；不要使用不带 `region` 参数的 `aliyun configure get`，因为完整配置可能包含凭证。
3. macOS/Linux 使用：

```bash
BIZ_REGION_ID="$(aliyun configure get region 2>/dev/null)"
```

Windows PowerShell 使用：

```powershell
$BizRegionId = aliyun configure get region
```

4. 如果没有读取到 Region，停止查询并提示用户执行一次 `aliyun configure set --region <region-id>`；正常情况下无需用户另外填写业务地域。
5. 使用解析出的地域执行下面的命令。正式环境不添加 `--endpoint`：

```bash
aliyun adb list-lake-storages \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --biz-region-id "$BIZ_REGION_ID"
```

仅当响应同时满足 `Success=true`、`Code=ok`、`HttpStatusCode=200` 时才接受结果。逐项提取非空的 `Items[].LakeStorageId`，该字段就是可选的 OSS Bucket 名称；不要把 `RegionId`、账号、权限或其它字段作为 Bucket 名称。

使用响应中的 `PageNumber`、`PageSize` 和 `TotalCount` 判断分页。当 `PageNumber * PageSize < TotalCount` 时，在下一次请求中追加 `--page-number <下一页页码> --page-size <当前每页数量>`，直至收集完全部页面的 `Items[].LakeStorageId`。将完整列表展示给用户选择，并把选中的 `LakeStorageId` 设置为 `OSS_BUCKET`；不得接受列表之外的值。

任一成功状态不满足时停止流程并报告响应中的 `Code` 和 `Message`。全部页面均没有非空的 `Items[].LakeStorageId` 时，按湖存储列表为空处理。

如果查询失败，原样报告错误并停止上传和入库。如果列表为空，停止流程并引导用户进入 [ADB 控制台](https://adb.console.aliyun.com/) 的目标集群，依次选择“数据管理 > 湖存储管理”，新建湖存储，并为当前 RAM 用户或角色新增读写授权。操作说明参见[如何使用湖存储](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/user-guide/lake-storage)。

如果用户提供现成的 `oss://` URI，其中的 Bucket 必须与最终选择的 `OSS_BUCKET` 一致。

## 7. 上传文件或目录到 OSS

> **路径前缀校验**：所有上传目标路径必须以 `oss://adb-lake-` 开头（即湖存储 Bucket）。如果解析出的 OSS URI 不符合此前缀，立即停止并告知用户仅支持 `adb-lake-` 前缀的湖存储 Bucket。

上传单文件：

```bash
aliyun oss cp ./report.pdf "oss://$OSS_BUCKET/knowledge/report.pdf"
```

上传整个目录：

```bash
aliyun oss cp ./data/ "oss://$OSS_BUCKET/knowledge/data/" --recursive
```

验证文件：

```bash
aliyun oss stat "oss://$OSS_BUCKET/knowledge/report.pdf"
```

部分 Bucket 可能不允许 `ls`，但仍允许上传和读取；这种情况使用 `stat` 验证已知对象。

**上传完成并通过 stat 验证后，必须立即执行入库（`add-knowledge-file`），无需等待用户额外下达入库指令。流程是：上传 → 验证(stat) → 入库，一气呵成。**

## 8. 入库一个文件

> **路径前缀校验**：`--file-location` 的值必须以 `oss://adb-lake-` 开头。不符合时停止操作并提示用户。

```bash
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/report.pdf" \
  --file-type pdf \
  --upload-user alice
```

参数说明：

| 参数 | 是否必填 | 说明 |
|------|----------|------|
| `--api-version` | 是 | 固定为 `2021-12-01` |
| `--db-cluster-id` | 是 | ADB 集群 ID |
| `--file-location` | 是 | 完整 `oss://` 文件地址 |
| `--file-type` | 否 | `pdf`、`csv`、`xlsx`、`txt` 等；可省略让服务识别 |
| `--upload-user` | 否 | 标记文件上传用户 |
| `--region` | 否 | 仅在 `ADB_REGION` 有值时添加 |

不传 `--is-dir` 时按单文件处理。`add-knowledge-file` 不保证幂等，不要自动重试成功或结果不明的请求。

## 9. 直接入库 OSS 目录

目录地址必须是 `oss://` URI，并显式设置 `--is-dir true`：

```bash
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/data/" \
  --is-dir true \
  --upload-user alice
```

目录请求被受理后，扫描、解析和索引仍可能异步进行。

## 10. 查询知识库召回

```bash
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "是否有产品授权书"
```

需要限制候选数时添加：

```bash
--topk 3
```

客户明确提供地域时，可在命令末尾添加：

```bash
--region "$ADB_REGION"
```

每次执行只发起一个召回请求，不自动重试。CLI 的 stdout、stderr 和退出码应原样返回，不解析、不归一化、不总结，也不假设响应字段固定。

## 11. 从安装到召回的完整流程

```bash
# 安装 CLI（macOS）
brew install aliyun-cli

# 安装 ADB 插件
aliyun plugin install --name aliyun-cli-adb

# 配置凭证
aliyun configure

# 设置运行参数
export ADB_INSTANCE_ID="amv-xxxxxxxxxxxxxx"

# 自动读取 aliyun CLI 当前 profile 的默认 Region
BIZ_REGION_ID="$(aliyun configure get region 2>/dev/null)"

# OSS_BUCKET 未配置时，先查询湖存储 Bucket；正式环境不添加 endpoint
aliyun adb list-lake-storages \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --biz-region-id "$BIZ_REGION_ID"

# 让用户从上面的返回列表中选择，不接受自定义名称
export OSS_BUCKET="<bucket-from-returned-list>"

# 上传文件
aliyun oss cp ./authorization.pdf "oss://$OSS_BUCKET/knowledge/authorization.pdf"

# 触发入库
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/authorization.pdf" \
  --file-type pdf \
  --upload-user alice

# 等待异步索引完成后召回
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "是否有产品授权书"
```

## 12. Dry-run

使用 CLI 自带的 `--cli-dry-run` 检查请求而不发送：

```bash
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "是否有产品授权书" \
  --cli-dry-run
```

## 13. 常见问题

### `aliyun adb` 或知识命令不存在

重新安装或更新公开 ADB 插件，并再次检查帮助信息。

### 目录路径报错

目录入库只接受完整 OSS URI，例如 `oss://example-bucket/knowledge/data/`，不要传本地路径或 HTTP URL。

### 湖存储 Bucket 列表为空

不要改用自建 OSS Bucket。进入 [ADB 控制台](https://adb.console.aliyun.com/) 的目标集群，在“数据管理 > 湖存储管理”中新建湖存储，并为当前 RAM 用户或角色新增读写授权，然后重新查询列表。
