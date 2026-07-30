---
name: alibaba-adb-knowledge
description: Use the Alibaba Cloud CLI directly to discover and select an AnalyticDB lake-storage bucket, upload local or NAS files to OSS, add OSS files or directories to a knowledge base, and call knowledge recall for external customer environments. Needs to install or configure the public ADB CLI plugin, select a lake bucket, ingest a single knowledge file, ingest an OSS directory with isDir, attach uploadUser, run get-knowledge-recall, or troubleshoot customer CLI usage.
---

# ADB Knowledge

Run `aliyun` commands directly. Do not create, invoke, or depend on a wrapper script.

Read [README.md](README.md) when the user needs CLI installation, credential setup, permissions, or a complete end-to-end walkthrough.

## End-to-end workflow

Every task that involves uploading or ingesting files must follow these four steps in strict order:

1. **Environment check** — Verify the CLI, ADB plugin, and required parameters are available (see "Install and verify the CLI").
2. **Bucket selection** — Execute `list-lake-storages`, extract `Items[].LakeStorageId`, present those values to the user, and let them choose exactly one bucket. This is a mandatory prerequisite; do not skip it or assume a bucket.
3. **Upload + Ingest** — Upload the file(s) to OSS → verify with `aliyun oss stat` → immediately execute `add-knowledge-file`. These three actions are a single atomic sequence; do not wait for a separate user instruction between them.
4. **Recall** — `get-knowledge-recall` with full raw output returned verbatim.

**Step 2 (Bucket selection) is an independent prerequisite that must complete before any upload or ingestion operation begins.**

## Path validation

Every OSS target path (for upload) and every `--file-location` value (for ingestion) **must** start with `oss://adb-lake-`. This ensures only lake-storage buckets are used.

Before executing `aliyun oss cp` or `aliyun adb add-knowledge-file`, validate the resolved OSS URI:
- ✅ `oss://adb-lake-cn-beijing-9746ll8740/knowledge/report.pdf` — valid
- ❌ `oss://my-custom-bucket/knowledge/report.pdf` — rejected

If the path does not match the `oss://adb-lake-` prefix, **stop immediately** and inform the user that only lake-storage buckets (prefixed with `adb-lake-`) are supported. Do not proceed with upload or ingestion.

## Constants and configuration

Use API version `2021-12-01` for every ADB knowledge command.

Require the ADB cluster ID. Prefer `ADB_INSTANCE_ID` when it is available:

```bash
export ADB_INSTANCE_ID="amv-xxxxxxxxxxxxxx"
```

Resolve the business region for lake-bucket discovery automatically from the active aliyun CLI profile with `aliyun configure get region`. Do not ask the user to supply a separate business-region value when the CLI region is configured. This command returns only the configured Region; do not use bare `aliyun configure get`, which may expose credentials.

Treat the standard region override as an optional customer-supplied value for ingestion and recall:

```bash
export ADB_REGION="<region-id>"
```

When constructing any ADB command:

- Append `--region "$ADB_REGION"` only when `ADB_REGION` is non-empty.
- Omit `--region` entirely when the variable is absent.
- Do not add `--endpoint` in the customer skill.
- Do not invent a region default.

## Install and verify the CLI

Install the ADB plugin from the public plugin registry:

```bash
aliyun plugin install --name aliyun-cli-adb
```

Update an existing installation when necessary:

```bash
aliyun plugin update --name aliyun-cli-adb
```

Verify the required commands and parameters:

```bash
aliyun version
aliyun plugin show --name aliyun-cli-adb
aliyun adb list-lake-storages --api-version 2021-12-01 --help
aliyun adb add-knowledge-file --api-version 2021-12-01 --help
aliyun adb get-knowledge-recall --api-version 2021-12-01 --help
```

Require `list-lake-storages` to expose `--biz-region-id`, `--page-number`, and `--page-size`. Require `add-knowledge-file` to expose `--is-dir` and `--upload-user`. Require `get-knowledge-recall` to expose `--topk` and the global `--read-timeout` option.

## Resolve the lake-storage bucket

Complete this workflow before every upload or `add-knowledge-file` request:

1. Check `OSS_BUCKET` first.
2. If `OSS_BUCKET` is non-empty, use it as the preconfigured lake-storage bucket. It must have been selected from `list-lake-storages`; never accept a custom bucket name.
3. If `OSS_BUCKET` is empty, resolve the business region automatically from the active aliyun CLI profile:

```bash
BIZ_REGION_ID="$(aliyun configure get region 2>/dev/null)"
```

4. If `BIZ_REGION_ID` is empty, stop before calling `list-lake-storages` and ask the user to configure the CLI default region once with `aliyun configure set --region <region-id>`.
5. Issue the following command without `--endpoint`:

```bash
aliyun adb list-lake-storages \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --biz-region-id "$BIZ_REGION_ID"
```

Accept the response only when `Success` is `true`, `Code` is `ok`, and `HttpStatusCode` is `200`. Extract each non-empty `Items[].LakeStorageId`; every extracted `LakeStorageId` is a selectable OSS bucket name. Do not use `RegionId`, account, permission, or other response fields as the bucket name.

Use `PageNumber`, `PageSize`, and `TotalCount` to detect more pages. While `PageNumber * PageSize < TotalCount`, request the next page by appending `--page-number <next-page-number> --page-size <current-page-size>` and collect its `Items[].LakeStorageId`. Show the complete collected list and ask the user to choose exactly one. Set `OSS_BUCKET` to the selected `LakeStorageId` only; never synthesize or accept a value that is not in the list.

If any success-status check fails, stop and report the response `Code` and `Message`. If all pages contain no non-empty `Items[].LakeStorageId`, treat the lake-storage list as empty.

If the command fails, stop and return the error before uploading or reporting ingestion. If the list is empty, stop before upload or ingestion and direct the user to the AnalyticDB for MySQL console: open the target cluster, choose **Data Management > Lake Storage Management**, create lake storage, and add read/write authorization for the current RAM user or role. Do not continue until a lake bucket is available.

If the user supplies an existing `oss://` URI, require its bucket component to match the resolved `OSS_BUCKET`.

## Upload local content to OSS

> **Path prefix constraint**: the target OSS path must start with `oss://adb-lake-`; see [Path validation](#path-validation).

Upload one file:

```bash
aliyun oss cp ./report.pdf "oss://$OSS_BUCKET/knowledge/report.pdf"
```

Upload a directory recursively:

```bash
aliyun oss cp ./data/ "oss://$OSS_BUCKET/knowledge/data/" --recursive
```

Verify a known object with `aliyun oss stat`. Do not rely on bucket listing permission being available.

**After upload and stat verification succeed, immediately proceed to execute `add-knowledge-file` (see next section). Do not wait for a separate user instruction. The sequence upload → stat → add-knowledge-file is a single atomic flow.**

## Add one knowledge file

> **Path prefix constraint**: `--file-location` must start with `oss://adb-lake-`; see [Path validation](#path-validation).

Require a complete `oss://` location. Add optional parameters only when the user supplies values:

```bash
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/report.pdf" \
  --file-type pdf \
  --upload-user alice
```

Omit `--file-type`, `--upload-user`, or `--region` when the corresponding value is absent. Do not pass `--is-dir false`; omission preserves single-file behavior.

Treat `add-knowledge-file` as non-idempotent. Never retry it automatically.

## Add an OSS directory

Require the directory itself to use an `oss://` URI. Set `--is-dir true` explicitly:

```bash
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/data/" \
  --is-dir true \
  --upload-user alice
```

Do not expand a directory into repeated file-level ingestion calls unless the user explicitly requests that behavior.

## Recall knowledge

Issue exactly one CLI request. Always pass the 300-second timeout as the CLI parameter `--read-timeout 300`:

```bash
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "是否有产品授权书"
```

Append `--topk <positive-integer>` only when requested. Append `--region` only when the customer supplies it.

Do not retry recall automatically, including on `EOF`, timeout, 429/5xx, or empty output. Wait up to the CLI timeout unless the user requests cancellation.

Return CLI stdout, stderr, and the exit status verbatim. Do not parse, normalize, summarize, redact, or assume any response fields because the response schema may change.

## Optional region example

When the customer explicitly provides a region, append it to the command:

```bash
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "是否有产品授权书" \
  --region "$ADB_REGION"
```

## Final response

For upload, verification, and ingestion operations, return only whether the user-requested file or directory succeeded. Use exactly one applicable one-line shape:

- `上传成功：<用户请求的文件或目录>。`
- `入库成功：<用户请求的文件或目录>。`
- `上传并入库成功：<用户请求的文件或目录>。`
- `上传失败：<用户请求的文件或目录>。`
- `入库失败：<用户请求的文件或目录>。`

Use the path or label from the user's request; never embed a concrete case in this skill. When `add-knowledge-file` exits successfully and returns `{}`, treat ingestion as successful and suppress the `{}` response body.

Do not include environment checks, CLI/plugin versions, region, bucket-selection steps, object counts, file-size observations, OSS metadata, response bodies, exit status, asynchronous-indexing explanations, warnings, full commands, or follow-up offers. On failure, append one short error reason only when it is necessary for the user's next action.

- Do not apply this compact-summary rule to recall. Recall must continue to return the complete raw stdout, stderr, and exit status as specified above.

## Safety

- Never expose AccessKey secrets or STS tokens.
- Redact the OSS bucket only in upload or ingestion summaries; do not modify raw recall output.
- Treat successful ingestion as request acceptance without claiming asynchronous indexing has completed.
- Use `--cli-dry-run` when command construction needs inspection without sending a request.
