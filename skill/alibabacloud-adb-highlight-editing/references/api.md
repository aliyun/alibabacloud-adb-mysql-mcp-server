# Highlight Service API Reference

The user must supply only the public service origin (scheme, host, and
optional port), for example:

```text
http://service.example:8000
```

The CLI appends the fixed `/api/v1/operators` path itself and tolerates an
origin that already includes it. It has no built-in service address and no
environment-variable fallback.

## Routes

| Operation | Submit | Query |
|---|---|---|
| Extract | `POST /highlight-extraction/tasks` | `GET /highlight-extraction/tasks/{task_id}` |
| Continuous/story cut | `POST /highlight-editing/tasks` | `GET /highlight-editing/tasks/{task_id}` |

Tasks transition through `PENDING`, `RUNNING`, and `SUCCESS`; terminal errors use
`FAILED` or `PARTIAL_SUCCESS`.

## Input Mapping

All tasks accept 1–20 ordered `media_inputs` and a
`highlight_description` of at most 2,000 characters.

Each input must be a complete public Alibaba OSS regional HTTP(S) file URL with
OSS V1 or V4 pre-signature query parameters. The CLI rejects unsigned URLs,
generic HTTP URLs, internal OSS URLs, bucket URLs, and prefix URLs. It converts
the public OSS hostname to its `-internal` counterpart without changing the
object path or signature query. Validation is syntactic; Alibaba OSS ultimately
validates whether the signature is authentic and unexpired.

Extraction defaults:

- clip duration: 10–15 seconds, strict;
- playback speed: 0.8–1.2;
- `per_max_clip_count`: service-selected unless `--max-clips` is passed;
- platform export enabled unless `--no-export` is passed.

Editing defaults:

- `output_count=1`;
- `target_duration=120`;
- opening hook duration 10 seconds;
- platform export enabled.

`CONTINUOUS` always sends `per_media_target_duration=null` and
`require_all_media=false`. `STORY_CUT` preserves input media order and treats
all inputs as a candidate pool with `require_all_media=false` by default. Pass
`--require-all-media` only when every input must appear in each generated
output. Supplying an episode range does not imply that requirement.

Platform result URLs may contain an internal OSS host. The CLI maps that host
to the matching public endpoint before downloading, while preserving the
signature query unchanged.

## Terminal Errors

Common server error codes:

- `MEDIA_UNAVAILABLE`, `MEDIA_INVALID`, `MEDIA_LIMIT_EXCEEDED`
- `ASR_FAILED`
- `MODEL_FAILED`, `MODEL_OUTPUT_INVALID`
- `PLAN_INVALID`
- `RENDER_FAILED`, `UPLOAD_FAILED`
- `INTERNAL_ERROR`

The CLI exits with `0` on success, `1` for validation, service, polling, or
download failures, and argparse's `2` when required command-line arguments are
missing.
