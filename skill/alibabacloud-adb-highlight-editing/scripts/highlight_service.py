#!/usr/bin/env python3
"""Call the deployed highlight service and download exported results."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 14_400.0
DEFAULT_POLL_INTERVAL_SECONDS = 15.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
MAX_MEDIA_COUNT = 20
API_PATH_PREFIX = "api/v1/operators"
PUBLIC_OSS_HOST_PATTERN = re.compile(
    r"^(?:(?P<bucket>[a-z0-9][a-z0-9-]{1,61}[a-z0-9])\.)?"
    r"(?P<endpoint>oss-(?!accelerate(?:\.|$))[a-z0-9-]+)"
    r"\.aliyuncs\.com$"
)
V1_SIGNATURE_PARAMETERS = frozenset(
    {"ossaccesskeyid", "expires", "signature"}
)
V4_SIGNATURE_PARAMETERS = frozenset(
    {
        "x-oss-signature-version",
        "x-oss-credential",
        "x-oss-date",
        "x-oss-expires",
        "x-oss-signature",
    }
)


class Operation(StrEnum):
    EXTRACT = "extract"
    CONTINUOUS = "continuous"
    STORY_CUT = "story-cut"


class TaskKind(StrEnum):
    EXTRACTION = "extraction"
    EDITING = "editing"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


class HighlightServiceError(RuntimeError):
    """Raised when input preparation or service execution fails."""


def normalize_presigned_oss_url(url: str) -> str:
    """Validate a public Alibaba OSS pre-signed file URL and use its internal host."""
    normalized = url.strip()
    parsed = urlsplit(normalized)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise HighlightServiceError(
            "Media must be a public Alibaba OSS pre-signed HTTP(S) URL."
        )
    hostname = (parsed.hostname or "").lower()
    host_match = PUBLIC_OSS_HOST_PATTERN.fullmatch(hostname)
    if (
        host_match is None
        or host_match.group("endpoint").endswith("-internal")
    ):
        raise HighlightServiceError(
            "Media host must be a public regional Alibaba OSS endpoint."
        )
    if parsed.username or parsed.password or parsed.port is not None:
        raise HighlightServiceError(
            "Media URL must not contain user info or an explicit port."
        )
    if parsed.fragment:
        raise HighlightServiceError("Media URL must not contain a fragment.")
    path_parts = [part for part in parsed.path.split("/") if part]
    required_path_parts = 1 if host_match.group("bucket") else 2
    if (
        len(path_parts) < required_path_parts
        or not parsed.path
        or parsed.path.endswith("/")
    ):
        raise HighlightServiceError(
            "Media URL must identify one OSS file, not a bucket or prefix."
        )

    query_parameters = {
        key.casefold(): value
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    }
    has_v1_signature = all(
        query_parameters.get(key) for key in V1_SIGNATURE_PARAMETERS
    )
    has_v4_signature = all(
        query_parameters.get(key) for key in V4_SIGNATURE_PARAMETERS
    )
    if not has_v1_signature and not has_v4_signature:
        raise HighlightServiceError(
            "Media URL is missing required OSS V1 or V4 pre-signature parameters."
        )

    internal_netloc = parsed.netloc.replace(
        ".aliyuncs.com",
        "-internal.aliyuncs.com",
        1,
    )
    return urlunsplit(
        (
            parsed.scheme,
            internal_netloc,
            parsed.path,
            parsed.query,
            "",
        )
    )


def resolve_media_uris(media_uris: Sequence[str]) -> list[str]:
    """Validate ordered pre-signed OSS file URLs and map them to internal hosts."""
    if not media_uris:
        raise HighlightServiceError("At least one media input is required.")
    resolved = [normalize_presigned_oss_url(uri) for uri in media_uris]
    unique_resolved = list(dict.fromkeys(resolved))
    if len(unique_resolved) > MAX_MEDIA_COUNT:
        raise HighlightServiceError(
            f"Received {len(unique_resolved)} media files; the API limit is "
            f"{MAX_MEDIA_COUNT}."
        )
    return unique_resolved


def _normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HighlightServiceError("API base URL must be an HTTP(S) URL.")
    path = parsed.path.rstrip("/")
    if not path.endswith(f"/{API_PATH_PREFIX}"):
        path = f"{path}/{API_PATH_PREFIX}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _route_for_operation(operation: Operation) -> str:
    if operation is Operation.EXTRACT:
        return "highlight-extraction/tasks"
    return "highlight-editing/tasks"


def _build_payload(
    args: argparse.Namespace,
    operation: Operation,
    media_uris: list[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "media_inputs": [{"uri": uri} for uri in media_uris],
        "highlight_description": args.highlight_description,
        "output": {"need_export": args.need_export},
    }
    if operation is Operation.EXTRACT:
        payload.update(
            {
                "per_max_clip_count": args.max_clips,
                "duration": {
                    "min": args.min_duration,
                    "max": args.max_duration,
                    "strict": args.strict_duration,
                    "playback_speed_range": {
                        "min": args.speed_min,
                        "max": args.speed_max,
                    },
                },
            }
        )
        return payload

    mode = (
        "CONTINUOUS"
        if operation is Operation.CONTINUOUS
        else "STORY_CUT"
    )
    payload["editing"] = {
        "mode": mode,
        "output_count": args.output_count,
        "target_duration": args.target_duration,
        "per_media_target_duration": (
            None
            if operation is Operation.CONTINUOUS
            else args.per_media_target_duration
        ),
        "require_all_media": (
            False
            if operation is Operation.CONTINUOUS
            else args.require_all_media
        ),
        "opening_hook": {
            "description": args.opening_description,
            "target_duration": args.opening_duration,
        },
    }
    return payload


class HighlightApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        request_timeout_seconds: float,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        if request_timeout_seconds <= 0:
            raise HighlightServiceError(
                "HTTP request timeout must be greater than zero."
            )
        self.request_timeout_seconds = request_timeout_seconds

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False).encode()
            if payload is not None
            else None
        )
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        started_at = time.monotonic()
        try:
            with urlopen(request, timeout=self.request_timeout_seconds) as response:
                raw = json.loads(response.read().decode())
        except HTTPError as exc:
            message = f"HTTP {exc.code}"
            try:
                error_payload = json.loads(exc.read().decode())
                message = error_payload.get("message") or message
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            raise HighlightServiceError(f"Service request failed: {message}") from exc
        except (URLError, TimeoutError) as exc:
            raise HighlightServiceError("Service request failed.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HighlightServiceError(
                "Service returned an invalid JSON response."
            ) from exc
        elapsed_seconds = time.monotonic() - started_at
        print(
            f"HTTP {method} completed: elapsed_seconds={elapsed_seconds:.3f}",
            file=sys.stderr,
        )
        if not isinstance(raw, dict) or raw.get("status") != "SUCCESS":
            message = raw.get("message") if isinstance(raw, dict) else None
            raise HighlightServiceError(
                f"Service returned a non-success status: {message or 'unknown error'}"
            )
        if not isinstance(raw.get("data"), dict):
            raise HighlightServiceError("Service response is missing data.")
        return raw

    def submit(self, route: str, payload: dict[str, Any]) -> str:
        raw = self._request_json("POST", route, payload)
        task_id = raw["data"].get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise HighlightServiceError("Submit response is missing task_id.")
        return task_id

    def query(self, route: str, task_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"{route}/{task_id}")

    def wait(
        self,
        route: str,
        task_id: str,
        *,
        timeout_seconds: float,
        poll_interval_seconds: float,
        stderr: TextIO,
    ) -> dict[str, Any]:
        if timeout_seconds <= 0 or poll_interval_seconds < 0:
            raise HighlightServiceError(
                "Polling timeout must be positive and interval non-negative."
            )
        deadline = time.monotonic() + timeout_seconds
        last_status: str | None = None
        consecutive_failures = 0
        started_at = time.monotonic()
        while time.monotonic() < deadline:
            try:
                raw = self.query(route, task_id)
                consecutive_failures = 0
            except HighlightServiceError:
                consecutive_failures += 1
                if consecutive_failures > 3:
                    raise
                retry_delay = min(
                    max(poll_interval_seconds, 1.0)
                    * (2 ** (consecutive_failures - 1)),
                    30.0,
                )
                print(
                    "Transient task query failed; "
                    f"retrying_in_seconds={retry_delay:.1f}",
                    file=stderr,
                )
                time.sleep(retry_delay)
                continue

            status_value = raw["data"].get("task_status")
            if status_value != last_status:
                print(
                    f"Task status changed: task_id={task_id} status={status_value}",
                    file=stderr,
                )
                last_status = status_value
            if status_value == TaskStatus.SUCCESS.value:
                elapsed_seconds = time.monotonic() - started_at
                print(
                    "Task completed: "
                    f"task_id={task_id} elapsed_seconds={elapsed_seconds:.3f}",
                    file=stderr,
                )
                return raw
            if status_value in {
                TaskStatus.FAILED.value,
                TaskStatus.PARTIAL_SUCCESS.value,
            }:
                error = raw["data"].get("error") or {}
                code = error.get("code") or status_value
                message = error.get("message") or "Task failed."
                raise HighlightServiceError(f"{code}: {message}")
            if status_value not in {
                TaskStatus.PENDING.value,
                TaskStatus.RUNNING.value,
            }:
                raise HighlightServiceError(
                    f"Task returned an unknown status: {status_value}"
                )
            time.sleep(poll_interval_seconds)
        raise HighlightServiceError(
            f"Task {task_id} did not finish within {timeout_seconds:.0f} seconds."
        )


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_sensitive(item)
            for key, item in value.items()
            if key.lower()
            not in {
                "access_key",
                "authorization",
                "password",
                "secret_key",
                "source_ak",
                "source_sk",
            }
        }
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value


def _output_urls(
    operation: Operation,
    response: dict[str, Any],
) -> list[tuple[str, str]]:
    data = response["data"]
    output: list[tuple[str, str]] = []
    if operation is Operation.EXTRACT:
        for media in data.get("media_results") or []:
            media_index = int(media["media_index"])
            for clip in media.get("clips") or []:
                url = clip.get("output_url")
                if url:
                    output.append(
                        (
                            f"highlight-m{media_index:02d}-c{int(clip['index']):02d}",
                            url,
                        )
                    )
        return output

    for item in data.get("outputs") or []:
        url = item.get("output_url")
        if url:
            output.append((f"{operation.value}-{int(item['index']):02d}", url))
    return output


def downloadable_output_url(url: str) -> str:
    """Map Alibaba Cloud internal OSS output hosts to public hosts."""
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if ".oss-" not in hostname or not hostname.endswith(
        "-internal.aliyuncs.com"
    ):
        return url
    public_netloc = parsed.netloc.replace(
        "-internal.aliyuncs.com",
        ".aliyuncs.com",
        1,
    )
    return urlunsplit(
        (
            parsed.scheme,
            public_netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _download(
    url: str,
    destination: Path,
    *,
    request_timeout_seconds: float,
) -> int:
    temporary = destination.with_suffix(destination.suffix + ".part")
    started_at = time.monotonic()
    try:
        request = Request(downloadable_output_url(url), method="GET")
        with urlopen(request, timeout=request_timeout_seconds) as response:
            with temporary.open("wb") as output_file:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output_file.write(chunk)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    elapsed_seconds = time.monotonic() - started_at
    size_bytes = destination.stat().st_size
    print(
        "Output downloaded: "
        f"path={destination} size_bytes={size_bytes} "
        f"elapsed_seconds={elapsed_seconds:.3f}",
        file=sys.stderr,
    )
    return size_bytes


def _download_outputs(
    operation: Operation,
    response: dict[str, Any],
    output_dir: Path,
    *,
    request_timeout_seconds: float,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloads: list[dict[str, Any]] = []
    for stem, url in _output_urls(operation, response):
        suffix = Path(urlsplit(url).path).suffix or ".mp4"
        destination = output_dir / f"{stem}{suffix}"
        try:
            size_bytes = _download(
                url,
                destination,
                request_timeout_seconds=request_timeout_seconds,
            )
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise HighlightServiceError(
                f"Failed to download output {stem}."
            ) from exc
        downloads.append(
            {
                "path": str(destination.absolute()),
                "size_bytes": size_bytes,
            }
        )
    return downloads


def _default_output_dir(operation: Operation) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / "highlight-results" / f"{timestamp}-{operation.value}"


def _add_common_task_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--media",
        action="append",
        required=True,
        help=(
            "Public Alibaba OSS pre-signed HTTP(S) file URL. "
            "Repeat for multiple ordered inputs."
        ),
    )
    parser.add_argument("--highlight-description", default="")
    parser.add_argument(
        "--api-base-url",
        required=True,
        help=(
            "Public highlight service origin (scheme, host, optional "
            "port). The CLI appends /api/v1/operators automatically."
        ),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--no-export",
        action="store_false",
        dest="need_export",
        help="Return timeline metadata without rendering or downloading videos.",
    )
    parser.set_defaults(need_export=True)
    parser.add_argument("--submit-only", action="store_true")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )


def _add_editing_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-count", type=int, default=1)
    parser.add_argument("--target-duration", type=float, default=120.0)
    parser.add_argument("--opening-description", default="")
    parser.add_argument("--opening-duration", type=float, default=10.0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Submit high extraction, continuous edit, or story cut tasks and "
            "download exported outputs."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extraction = subparsers.add_parser(Operation.EXTRACT.value)
    _add_common_task_arguments(extraction)
    extraction.add_argument("--max-clips", type=int)
    extraction.add_argument("--min-duration", type=float, default=10.0)
    extraction.add_argument("--max-duration", type=float, default=15.0)
    extraction.add_argument(
        "--non-strict-duration",
        action="store_false",
        dest="strict_duration",
    )
    extraction.set_defaults(strict_duration=True)
    extraction.add_argument("--speed-min", type=float, default=0.8)
    extraction.add_argument("--speed-max", type=float, default=1.2)

    continuous = subparsers.add_parser(Operation.CONTINUOUS.value)
    _add_common_task_arguments(continuous)
    _add_editing_arguments(continuous)

    story_cut = subparsers.add_parser(Operation.STORY_CUT.value)
    _add_common_task_arguments(story_cut)
    _add_editing_arguments(story_cut)
    story_cut.add_argument("--per-media-target-duration", type=float)
    story_cut.add_argument(
        "--require-all-media",
        action="store_true",
        default=False,
        help=(
            "Require every input media item to appear in each output. "
            "Disabled by default."
        ),
    )

    status = subparsers.add_parser("status")
    status.add_argument(
        "--kind",
        choices=[item.value for item in TaskKind],
        required=True,
    )
    status.add_argument("--task-id", required=True)
    status.add_argument("--api-base-url", required=True)
    status.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )

    download = subparsers.add_parser("download")
    download.add_argument(
        "--operation",
        choices=[item.value for item in Operation],
        required=True,
    )
    download.add_argument("--task-id", required=True)
    download.add_argument("--api-base-url", required=True)
    download.add_argument("--output-dir", type=Path, required=True)
    download.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    return parser


def _validate_task_args(args: argparse.Namespace, operation: Operation) -> None:
    if operation is Operation.EXTRACT:
        if args.max_clips is not None and not 1 <= args.max_clips <= 10:
            raise HighlightServiceError("--max-clips must be between 1 and 10.")
        if args.min_duration <= 0 or args.max_duration < args.min_duration:
            raise HighlightServiceError(
                "Extraction duration must satisfy 0 < min <= max."
            )
        if not 0.8 <= args.speed_min <= args.speed_max <= 1.2:
            raise HighlightServiceError(
                "Playback speed must satisfy 0.8 <= min <= max <= 1.2."
            )
        return
    if not 1 <= args.output_count <= 10:
        raise HighlightServiceError("--output-count must be between 1 and 10.")
    if args.target_duration <= 0:
        raise HighlightServiceError("--target-duration must be greater than zero.")
    if not 0 < args.opening_duration < args.target_duration:
        raise HighlightServiceError(
            "--opening-duration must be greater than zero and less than "
            "--target-duration."
        )
    if (
        operation is Operation.STORY_CUT
        and args.per_media_target_duration is not None
        and args.per_media_target_duration <= 0
    ):
        raise HighlightServiceError(
            "--per-media-target-duration must be greater than zero."
        )


def _execute_task(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    operation = Operation(args.command)
    _validate_task_args(args, operation)
    media_uris = resolve_media_uris(args.media)
    payload = _build_payload(args, operation, media_uris)
    client = HighlightApiClient(
        args.api_base_url,
        request_timeout_seconds=args.request_timeout,
    )
    route = _route_for_operation(operation)
    task_id = client.submit(route, payload)
    print(f"Task submitted: task_id={task_id}", file=stderr)
    if args.submit_only:
        print(
            json.dumps(
                {"task_id": task_id, "task_status": TaskStatus.PENDING.value},
                ensure_ascii=False,
            ),
            file=stdout,
        )
        return 0

    started_at = time.monotonic()
    response = client.wait(
        route,
        task_id,
        timeout_seconds=args.timeout,
        poll_interval_seconds=args.poll_interval,
        stderr=stderr,
    )
    output_dir = args.output_dir or _default_output_dir(operation)
    downloads = (
        _download_outputs(
            operation,
            response,
            output_dir,
            request_timeout_seconds=args.request_timeout,
        )
        if args.need_export
        else []
    )
    elapsed_seconds = time.monotonic() - started_at
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    result_path.write_text(
        json.dumps(_redact_sensitive(response), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = {
        "operation": operation.value,
        "task_id": task_id,
        "task_status": response["data"]["task_status"],
        "elapsed_seconds": round(elapsed_seconds, 3),
        "output_dir": str(output_dir.resolve()),
        "result_path": str(result_path.resolve()),
        "downloads": downloads,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False), file=stdout)
    return 0


def _query_status(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
) -> int:
    client = HighlightApiClient(
        args.api_base_url,
        request_timeout_seconds=args.request_timeout,
    )
    route = (
        "highlight-extraction/tasks"
        if TaskKind(args.kind) is TaskKind.EXTRACTION
        else "highlight-editing/tasks"
    )
    response = client.query(route, args.task_id)
    print(
        json.dumps(_redact_sensitive(response), ensure_ascii=False, indent=2),
        file=stdout,
    )
    return 0


def _download_existing_task(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
) -> int:
    operation = Operation(args.operation)
    client = HighlightApiClient(
        args.api_base_url,
        request_timeout_seconds=args.request_timeout,
    )
    response = client.query(_route_for_operation(operation), args.task_id)
    if response["data"].get("task_status") != TaskStatus.SUCCESS.value:
        raise HighlightServiceError(
            "Only a successful task can be downloaded."
        )
    downloads = _download_outputs(
        operation,
        response,
        args.output_dir,
        request_timeout_seconds=args.request_timeout,
    )
    result_path = args.output_dir / "result.json"
    result_path.write_text(
        json.dumps(_redact_sensitive(response), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = {
        "operation": operation.value,
        "task_id": args.task_id,
        "task_status": response["data"]["task_status"],
        "output_dir": str(args.output_dir.resolve()),
        "result_path": str(result_path.resolve()),
        "downloads": downloads,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False), file=stdout)
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    try:
        args = _parser().parse_args(argv)
        if args.command == "status":
            return _query_status(args, stdout=output)
        if args.command == "download":
            return _download_existing_task(
                args,
                stdout=output,
            )
        return _execute_task(
            args,
            stdout=output,
            stderr=errors,
        )
    except HighlightServiceError as exc:
        print(f"Error: {exc}", file=errors)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
