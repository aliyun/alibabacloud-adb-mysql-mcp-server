# ADB Knowledge Customer Guide

English | [中文](README_CN.md)

This skill uses the Alibaba Cloud CLI directly to perform the following operations, without any extra wrapper scripts:

1. Upload local or NAS files to OSS.
2. Add a single OSS file or an entire OSS directory to the ADB knowledge base.
3. Query the ADB knowledge base recall with natural-language questions.

## End-to-end workflow

Any task involving upload or ingestion must strictly follow this four-step order:

1. **Environment check** — Verify the CLI, ADB plugin, and required parameters are available (see sections 1–4).
2. **Bucket selection** — Run `list-lake-storages`, extract `Items[].LakeStorageId`, present these bucket names to the user, and have the user pick one. This step is an independent prerequisite; never skip it or assume a bucket already exists.
3. **Upload + ingest** — Upload the file to OSS → verify with `aliyun oss stat` → immediately run `add-knowledge-file`. These three actions form one atomic sequence; do not wait for the user to issue a separate ingestion command.
4. **Recall** — Run `get-knowledge-recall` and output the result verbatim in full.

**Step 2 (bucket selection) is a standalone prerequisite that must be completed before any upload or ingestion operation.**

## 1. Install the Alibaba Cloud CLI

Alibaba Cloud CLI 3.x is required.

### macOS

```bash
brew install aliyun-cli
```

### Linux

```bash
/bin/bash -c "$(curl -fsSL https://aliyuncli.alicdn.com/install.sh)"
```

### Windows

1. Download `https://aliyuncli.alicdn.com/aliyun-cli-windows-latest-amd64.zip`.
2. Extract `aliyun.exe` to a fixed directory.
3. Add that directory to the system `Path`.
4. Reopen the terminal.

Verify or upgrade:

```bash
aliyun version
aliyun upgrade --yes
```

## 2. Configure credentials

Interactive configuration:

```bash
aliyun configure
```

Alternatively, use the Alibaba Cloud CLI credential environment variables:

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID="<access-key-id>"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="<access-key-secret>"
export ALIBABA_CLOUD_SECURITY_TOKEN="<sts-token>"  # STS only
```

Prefer RAM roles or temporary credentials in production. Never commit AccessKey Secrets to a repository.

The current identity needs read/write access to the target OSS path, plus permissions for ADB knowledge file ingestion and knowledge recall.

## 3. Install the ADB plugin

Install from the public plugin source:

```bash
aliyun plugin install --name aliyun-cli-adb
```

If it is already installed, update it:

```bash
aliyun plugin update --name aliyun-cli-adb
```

## 4. Verify the installation

```bash
aliyun version
aliyun plugin show --name aliyun-cli-adb
aliyun adb list-lake-storages --api-version 2021-12-01 --help
aliyun adb add-knowledge-file --api-version 2021-12-01 --help
aliyun adb get-knowledge-recall --api-version 2021-12-01 --help
```

Confirm that:

- `list-lake-storages` includes `--biz-region-id`, `--page-number`, and `--page-size`.
- `add-knowledge-file` includes `--is-dir` and `--upload-user`.
- `get-knowledge-recall` is available and supports `--topk`.
- The CLI accepts the global `--read-timeout` parameter.

## 5. Set common environment variables

```bash
export ADB_INSTANCE_ID="amv-xxxxxxxxxxxxxx"
```

The `--biz-region-id` required for the lake-storage bucket query does not need to be set separately; the skill automatically uses the default region of the current aliyun CLI profile.

If the customer environment requires an explicitly specified standard region, then set:

```bash
export ADB_REGION="<region-id>"
```

`ADB_REGION` is optional. Add `--region` to ingestion or recall commands only when this variable has a value; omit the parameter entirely when it is unset. Customer-facing commands never add `--endpoint`.

`OSS_BUCKET` may only be set to an `Items[].LakeStorageId` returned by `list-lake-storages`; custom bucket names are not supported. If already configured, use it directly; otherwise query and select one as described in the next section.

## 6. Select a lake-storage bucket

`OSS_BUCKET` must be resolved before uploading files or submitting ingestion requests:

1. Check whether `OSS_BUCKET` already has a value; if so, use it as the pre-selected lake-storage bucket.
2. If not, automatically read the default region of the current profile via `aliyun configure get region`. This command returns only the region; do not use `aliyun configure get` without the `region` argument, because the full configuration may contain credentials.
3. On macOS/Linux use:

```bash
BIZ_REGION_ID="$(aliyun configure get region 2>/dev/null)"
```

On Windows PowerShell use:

```powershell
$BizRegionId = aliyun configure get region
```

4. If no region can be read, stop the query and prompt the user to run `aliyun configure set --region <region-id>` once; under normal circumstances the user does not need to provide a business region separately.
5. Run the following command with the resolved region. Do not add `--endpoint` in production:

```bash
aliyun adb list-lake-storages \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --biz-region-id "$BIZ_REGION_ID"
```

Accept the result only when the response satisfies `Success=true`, `Code=ok`, and `HttpStatusCode=200` simultaneously. Extract each non-empty `Items[].LakeStorageId`; this field is the selectable OSS bucket name. Do not treat `RegionId`, account, permission, or any other field as the bucket name.

Use `PageNumber`, `PageSize`, and `TotalCount` in the response to determine pagination. When `PageNumber * PageSize < TotalCount`, append `--page-number <next-page> --page-size <current-page-size>` to the next request until all pages' `Items[].LakeStorageId` values have been collected. Present the complete list to the user for selection and set the chosen `LakeStorageId` as `OSS_BUCKET`; values outside the list must not be accepted.

If any success condition is not met, stop the workflow and report the `Code` and `Message` from the response. If no non-empty `Items[].LakeStorageId` exists across all pages, treat the lake-storage list as empty.

If the query fails, report the error verbatim and stop both upload and ingestion. If the list is empty, stop the workflow and guide the user to the target cluster in the [ADB console](https://adb.console.aliyun.com/), navigate to "Data Management > Lake Storage Management", create a new lake storage, and grant read/write permissions to the current RAM user or role. See [How to use lake storage](https://help.aliyun.com/zh/analyticdb/analyticdb-for-mysql/user-guide/lake-storage) for instructions.

If the user provides a ready-made `oss://` URI, its bucket must match the finally selected `OSS_BUCKET`.

## 7. Upload a file or directory to OSS

> **Path prefix validation**: every upload target path must start with `oss://adb-lake-` (i.e. a lake-storage bucket). If the resolved OSS URI does not match this prefix, stop immediately and inform the user that only lake-storage buckets with the `adb-lake-` prefix are supported.

Upload a single file:

```bash
aliyun oss cp ./report.pdf "oss://$OSS_BUCKET/knowledge/report.pdf"
```

Upload an entire directory:

```bash
aliyun oss cp ./data/ "oss://$OSS_BUCKET/knowledge/data/" --recursive
```

Verify the file:

```bash
aliyun oss stat "oss://$OSS_BUCKET/knowledge/report.pdf"
```

Some buckets may disallow `ls` while still allowing upload and read; in that case use `stat` to verify known objects.

**After the upload completes and is verified with stat, run the ingestion (`add-knowledge-file`) immediately without waiting for a separate ingestion command from the user. The flow is: upload → verify (stat) → ingest, in one uninterrupted sequence.**

## 8. Ingest a single file

> **Path prefix validation**: the value of `--file-location` must start with `oss://adb-lake-`. Stop and prompt the user if it does not.

```bash
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/report.pdf" \
  --file-type pdf \
  --upload-user alice
```

Parameter reference:

| Parameter | Required | Description |
|------|----------|------|
| `--api-version` | Yes | Fixed to `2021-12-01` |
| `--db-cluster-id` | Yes | ADB cluster ID |
| `--file-location` | Yes | Full `oss://` file address |
| `--file-type` | No | `pdf`, `csv`, `xlsx`, `txt`, etc.; can be omitted to let the service detect it |
| `--upload-user` | No | Marks the file's uploading user |
| `--region` | No | Add only when `ADB_REGION` has a value |

Without `--is-dir`, the request is treated as a single file. `add-knowledge-file` is not guaranteed to be idempotent; do not automatically retry requests that succeeded or whose outcome is unclear.

## 9. Ingest an OSS directory directly

The directory address must be an `oss://` URI, with `--is-dir true` set explicitly:

```bash
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/data/" \
  --is-dir true \
  --upload-user alice
```

After a directory request is accepted, scanning, parsing, and indexing may still proceed asynchronously.

## 10. Query knowledge base recall

```bash
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "Is there a product authorization letter"
```

To limit the number of candidates, add:

```bash
--topk 3
```

When the customer explicitly provides a region, append at the end of the command:

```bash
--region "$ADB_REGION"
```

Issue only one recall request per execution, with no automatic retries. Return the CLI's stdout, stderr, and exit code verbatim — no parsing, normalization, or summarization, and no assumptions about fixed response fields.

## 11. Full workflow from installation to recall

```bash
# Install the CLI (macOS)
brew install aliyun-cli

# Install the ADB plugin
aliyun plugin install --name aliyun-cli-adb

# Configure credentials
aliyun configure

# Set runtime parameters
export ADB_INSTANCE_ID="amv-xxxxxxxxxxxxxx"

# Automatically read the default region of the current aliyun CLI profile
BIZ_REGION_ID="$(aliyun configure get region 2>/dev/null)"

# When OSS_BUCKET is not configured, query lake-storage buckets first; do not add endpoint in production
aliyun adb list-lake-storages \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --biz-region-id "$BIZ_REGION_ID"

# Let the user choose from the returned list above; custom names are not accepted
export OSS_BUCKET="<bucket-from-returned-list>"

# Upload the file
aliyun oss cp ./authorization.pdf "oss://$OSS_BUCKET/knowledge/authorization.pdf"

# Trigger ingestion
aliyun adb add-knowledge-file \
  --api-version 2021-12-01 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --file-location "oss://$OSS_BUCKET/knowledge/authorization.pdf" \
  --file-type pdf \
  --upload-user alice

# Recall after asynchronous indexing completes
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "Is there a product authorization letter"
```

## 12. Dry-run

Use the CLI's built-in `--cli-dry-run` to inspect a request without sending it:

```bash
aliyun adb get-knowledge-recall \
  --api-version 2021-12-01 \
  --read-timeout 300 \
  --db-cluster-id "$ADB_INSTANCE_ID" \
  --question "Is there a product authorization letter" \
  --cli-dry-run
```

## 13. FAQ

### `aliyun adb` or knowledge commands do not exist

Reinstall or update the public ADB plugin, then check the help output again.

### Directory path errors

Directory ingestion only accepts full OSS URIs such as `oss://example-bucket/knowledge/data/`; do not pass local paths or HTTP URLs.

### Lake-storage bucket list is empty

Do not switch to a self-managed OSS bucket. Go to the target cluster in the [ADB console](https://adb.console.aliyun.com/), create a new lake storage under "Data Management > Lake Storage Management", grant read/write permissions to the current RAM user or role, then query the list again.
