---
name: alibabacloud-adb-highlight-editing
description: Use when a user provides Alibaba OSS pre-signed media URLs and asks for public highlight extraction, continuous editing (顺剪), or story-cut editing (混剪) with local downloads.
---

# ADB Highlight Editing

## Workflow

1. Identify the operation.

   | Intent | Command | API mode |
   |---|---|---|
   | 高光提取、提取片段 | `extract` | extraction |
   | 顺剪、按原剧情连续剪 | `continuous` | `CONTINUOUS` |
   | 混剪、组合高光剧情 | `story-cut` | `STORY_CUT` |

   Ask only when the mode is ambiguous.

2. Require the user to provide:
   - the public service origin (scheme, host, and optional port);
     the skill appends the fixed `/api/v1/operators` path itself;
   - one complete public Alibaba OSS pre-signed HTTP(S) file URL per input.

   Do not use a default API address. Do not accept a bucket, prefix, unsigned
   URL, arbitrary HTTP URL, or an OSS internal URL. Ask for complete URLs when
   any input is missing or invalid.

3. Convert each ordered media URL into one `--media` argument. Maximum: 20.
   The CLI validates a regional OSS host, a file path, and OSS V1 or V4
   pre-signature parameters. It then adds `-internal` to the OSS hostname while
   preserving the path and complete query string.

   Preserve story order. Treat the input media list as a candidate pool; an
   episode range does not require every input to appear in the output. Only
   pass `--require-all-media` when the user explicitly requires every input
   episode to appear in each output. "Use/process episodes 01–05" does not
   enable it.

4. Run `scripts/highlight_service.py` relative to this file. Pass the user's
   public service origin explicitly; the CLI appends `/api/v1/operators`.

   ```bash
   python "<skill-directory>/scripts/highlight_service.py" story-cut \
     --api-base-url 'http://service.example:8000' \
     --media '<complete-public-oss-pre-signed-url-for-episode-01>' \
     --media '<complete-public-oss-pre-signed-url-for-episode-02>' \
     --highlight-description '围绕核心冲突，保留铺垫、升级、转折和结果' \
     --target-duration 90 --output-count 1 \
     --output-dir "$PWD/highlight-results/story-cut"
   ```

   Use the command's `--help`. Read [references/api.md](references/api.md) for
   duration, hook, output-count, all-media, and error details.

5. Let the command poll to terminal status. Keep its session alive. Never
   resubmit because it is slow. GET retries are automatic; POST is not.

6. Report task ID, elapsed time, and downloaded paths from `summary.json`.
   Also retain redacted `result.json`. Explicitly report an empty result.

## Quick Reference

| Need | Arguments |
|---|---|
| 10–15s highlights | `extract --min-duration 10 --max-duration 15 --speed-min 0.8 --speed-max 1.2` |
| Continuous edit | `continuous --target-duration 120 --opening-duration 10` |
| Story cut (candidate pool by default) | `story-cut --target-duration 120 [--require-all-media only if explicit]` |
| Submit only | `--submit-only` |
| No rendered files | `--no-export` |
| Check task | `status --kind extraction\|editing --task-id TASK_ID --api-base-url URL` |
| Retry downloads | `download --operation extract\|continuous\|story-cut --task-id TASK_ID --api-base-url URL --output-dir PATH` |

## Failure Rules

- Invalid media URL: ask for a complete, unexpired public OSS pre-signed file
  URL. The CLI validates its structure; OSS validates the signature itself.
- `FAILED`: report error and task ID; do not resubmit without user direction.
- Timeout: preserve task ID and use `status`, not POST.
- Download failure: use `download` on the same successful task.
- Never expose OSS URL query parameters in chat or retained result files.
