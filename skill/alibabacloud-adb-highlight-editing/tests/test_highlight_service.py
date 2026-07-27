from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "highlight_service.py"
SKILL_PATH = SKILL_DIR / "SKILL.md"
OPENAI_YAML_PATH = SKILL_DIR / "agents" / "openai.yaml"


def signed_media_url(filename: str = "episode_01.mp4") -> str:
    return (
        "https://example-bucket.oss-cn-beijing.aliyuncs.com/"
        f"media/{filename}"
        "?x-oss-signature-version=OSS4-HMAC-SHA256"
        "&x-oss-credential=test-credential"
        "&x-oss-date=20260723T000000Z"
        "&x-oss-expires=86400"
        "&x-oss-signature=abc%2Bdef"
    )


def load_module():
    spec = importlib.util.spec_from_file_location("highlight_service", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load highlight service script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApiHandler(BaseHTTPRequestHandler):
    posts: list[tuple[str, dict[str, Any]]] = []
    mode = "extract"

    def log_message(self, *_: Any) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        type(self).posts.append((self.path, body))
        self._json(
            {
                "status": "SUCCESS",
                "message": None,
                "data": {"task_id": "task-1", "task_status": "PENDING"},
            }
        )

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/files/result.mp4":
            payload = b"video-result"
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        base = f"http://127.0.0.1:{self.server.server_port}"
        if type(self).mode == "extract":
            data = {
                "task_id": "task-1",
                "task_status": "SUCCESS",
                "need_export": True,
                "media_results": [
                    {
                        "media_index": 0,
                        "clips": [
                            {
                                "index": 0,
                                "start_time": 1.0,
                                "end_time": 11.0,
                                "duration": 10.0,
                                "playback_speed": 1.0,
                                "output_url": f"{base}/files/result.mp4?token=secret",
                            }
                        ],
                    }
                ],
                "error": None,
            }
        else:
            api_mode = (
                "CONTINUOUS"
                if type(self).mode == "continuous"
                else "STORY_CUT"
            )
            data = {
                "task_id": "task-1",
                "task_status": "SUCCESS",
                "mode": api_mode,
                "need_export": True,
                "outputs": [
                    {
                        "index": 0,
                        "duration": 10.0,
                        "opening_hook": {
                            "media_index": 0,
                            "start_time": 1.0,
                            "end_time": 11.0,
                        },
                        "media_results": [
                            {
                                "media_index": 0,
                                "start_time": 1.0,
                                "end_time": 11.0,
                                "playback_speed": 1.0,
                            }
                        ],
                        "output_url": f"{base}/files/result.mp4?token=secret",
                    }
                ],
                "error": None,
            }
        self._json({"status": "SUCCESS", "message": None, "data": data})

    def _json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class HighlightServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        ApiHandler.posts = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_script_exists_and_imports(self) -> None:
        self.assertTrue(SCRIPT_PATH.is_file())
        load_module()

    def test_skill_documents_presigned_oss_and_download_workflow(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")

        self.assertNotIn("TODO", content)
        for required_text in (
            "pre-signed",
            "--api-base-url",
            "public service origin",
            "-internal",
            "extract",
            "continuous",
            "story-cut",
            "poll",
            "download",
            "references/api.md",
        ):
            self.assertIn(required_text, content)
        for removed_text in (
            "ACCESS_KEY",
            "SECRET_KEY",
            "SOURCE_AK",
            "SOURCE_SK",
            "--oss-endpoint",
            "--oss-region",
            "oss://",
            "alibabacloud-oss-v2",
        ):
            self.assertNotIn(removed_text, content)

    def test_skill_identity_and_story_cut_media_semantics(self) -> None:
        content = SKILL_PATH.read_text(encoding="utf-8")
        normalized_content = " ".join(content.split())
        openai_yaml = OPENAI_YAML_PATH.read_text(encoding="utf-8")

        self.assertEqual("alibabacloud-adb-highlight-editing", SKILL_DIR.name)
        self.assertIn("name: alibabacloud-adb-highlight-editing", content)
        self.assertIn(
            "Treat the input media list as a candidate pool",
            normalized_content,
        )
        self.assertIn(
            "Only pass `--require-all-media` when the user explicitly requires "
            "every input episode to appear in each output.",
            normalized_content,
        )
        self.assertIn("$alibabacloud-adb-highlight-editing", openai_yaml)
        self.assertNotIn("$highlight-editing", openai_yaml)
        self.assertNotIn("$calling-highlight-service", openai_yaml)

    def test_v4_presigned_virtual_host_url_is_mapped_to_internal(self) -> None:
        module = load_module()
        public_url = signed_media_url()

        normalized = module.normalize_presigned_oss_url(public_url)

        self.assertEqual(
            public_url.replace(
                ".oss-cn-beijing.aliyuncs.com",
                ".oss-cn-beijing-internal.aliyuncs.com",
                1,
            ),
            normalized,
        )

    def test_v1_presigned_path_style_url_is_mapped_to_internal(self) -> None:
        module = load_module()
        public_url = (
            "http://oss-cn-beijing.aliyuncs.com/example-bucket/"
            "media/episode_01.mp4"
            "?OSSAccessKeyId=test-id&Expires=1784781501"
            "&Signature=abc%2Fdef"
        )

        self.assertEqual(
            public_url.replace(
                "oss-cn-beijing.aliyuncs.com",
                "oss-cn-beijing-internal.aliyuncs.com",
                1,
            ),
            module.normalize_presigned_oss_url(public_url),
        )

    def test_unsigned_non_oss_internal_and_prefix_urls_are_rejected(self) -> None:
        module = load_module()
        invalid_urls = [
            "https://example-bucket.oss-cn-beijing.aliyuncs.com/"
            "media/episode_01.mp4",
            "https://media.example/episode_01.mp4?Signature=secret",
            signed_media_url().replace(
                ".oss-cn-beijing.aliyuncs.com",
                ".oss-cn-beijing-internal.aliyuncs.com",
                1,
            ),
            signed_media_url("directory/"),
            "oss://example-bucket/media/episode_01.mp4",
        ]

        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(
                module.HighlightServiceError
            ):
                module.normalize_presigned_oss_url(url)

    def test_media_resolution_preserves_order_deduplicates_and_maps_hosts(self) -> None:
        module = load_module()
        episode_01 = signed_media_url("episode_01.mp4")
        episode_02 = signed_media_url("episode_02.mp4")

        resolved = module.resolve_media_uris(
            [episode_02, episode_01, episode_02]
        )

        self.assertEqual(
            [
                episode_02.replace(
                    ".oss-cn-beijing.aliyuncs.com",
                    ".oss-cn-beijing-internal.aliyuncs.com",
                    1,
                ),
                episode_01.replace(
                    ".oss-cn-beijing.aliyuncs.com",
                    ".oss-cn-beijing-internal.aliyuncs.com",
                    1,
                ),
            ],
            resolved,
        )

    def test_api_base_url_is_required_for_every_command(self) -> None:
        module = load_module()
        commands = [
            ["extract", "--media", signed_media_url()],
            ["status", "--kind", "extraction", "--task-id", "task-1"],
            [
                "download",
                "--operation",
                "extract",
                "--task-id",
                "task-1",
                "--output-dir",
                "/tmp/output",
            ],
        ]

        for command in commands:
            with self.subTest(command=command), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    module._parser().parse_args(command)

    def test_api_base_url_prefix_is_appended_and_deduplicated(self) -> None:
        module = load_module()
        expected = "http://host:8000/api/v1/operators"

        for supplied in (
            "http://host:8000",
            "http://host:8000/",
            "http://host:8000/api/v1/operators",
            "http://host:8000/api/v1/operators/",
        ):
            with self.subTest(supplied=supplied):
                self.assertEqual(
                    expected, module._normalize_base_url(supplied)
                )

    def test_internal_oss_output_url_is_mapped_to_public_download_host(self) -> None:
        module = load_module()

        normalized = module.downloadable_output_url(
            "http://output-bucket.oss-cn-beijing-internal.aliyuncs.com/"
            "result.mp4?x-oss-signature=secret"
        )

        self.assertEqual(
            "http://output-bucket.oss-cn-beijing.aliyuncs.com/"
            "result.mp4?x-oss-signature=secret",
            normalized,
        )

    def test_three_operations_submit_poll_and_download(self) -> None:
        module = load_module()
        base_url = (
            f"http://127.0.0.1:{self.server.server_port}"
        )
        cases = [
            (
                "extract",
                "highlight-extraction/tasks",
                None,
                "highlight-m00-c00.mp4",
            ),
            (
                "continuous",
                "highlight-editing/tasks",
                "CONTINUOUS",
                "continuous-00.mp4",
            ),
            (
                "story-cut",
                "highlight-editing/tasks",
                "STORY_CUT",
                "story-cut-00.mp4",
            ),
        ]

        for operation, route, editing_mode, filename in cases:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                ApiHandler.mode = operation
                stdout = io.StringIO()
                exit_code = module.main(
                    [
                        operation,
                        "--media",
                        signed_media_url(),
                        "--api-base-url",
                        base_url,
                        "--output-dir",
                        tmp,
                        "--poll-interval",
                        "0",
                        "--timeout",
                        "5",
                    ],
                    stdout=stdout,
                    stderr=io.StringIO(),
                )

                self.assertEqual(0, exit_code)
                request_path, payload = ApiHandler.posts[-1]
                self.assertEqual(
                    f"/api/v1/operators/{route}",
                    request_path,
                )
                if editing_mode is None:
                    self.assertNotIn("editing", payload)
                else:
                    self.assertEqual(editing_mode, payload["editing"]["mode"])
                downloaded = Path(tmp) / filename
                self.assertEqual(b"video-result", downloaded.read_bytes())
                summary = json.loads((Path(tmp) / "summary.json").read_text())
                self.assertEqual("task-1", summary["task_id"])
                self.assertEqual(str(downloaded), summary["downloads"][0]["path"])
                self.assertNotIn("token=secret", stdout.getvalue())

    def test_story_cut_all_media_is_opt_in(self) -> None:
        module = load_module()
        base_url = (
            f"http://127.0.0.1:{self.server.server_port}"
        )
        common_args = [
            "story-cut",
            "--media",
            signed_media_url("episode_01.mp4"),
            "--media",
            signed_media_url("episode_02.mp4"),
            "--api-base-url",
            base_url,
            "--submit-only",
        ]

        default_exit_code = module.main(
            common_args,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        self.assertEqual(0, default_exit_code)
        self.assertFalse(ApiHandler.posts[-1][1]["editing"]["require_all_media"])

        explicit_exit_code = module.main(
            [*common_args, "--require-all-media"],
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        self.assertEqual(0, explicit_exit_code)
        self.assertTrue(ApiHandler.posts[-1][1]["editing"]["require_all_media"])

    def test_download_command_reuses_existing_task_without_post(self) -> None:
        module = load_module()
        ApiHandler.mode = "extract"
        base_url = (
            f"http://127.0.0.1:{self.server.server_port}"
        )

        with tempfile.TemporaryDirectory() as tmp:
            exit_code = module.main(
                [
                    "download",
                    "--operation",
                    "extract",
                    "--task-id",
                    "task-1",
                    "--api-base-url",
                    base_url,
                    "--output-dir",
                    tmp,
                ],
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )

            self.assertEqual(0, exit_code)
            self.assertEqual([], ApiHandler.posts)
            self.assertEqual(
                b"video-result",
                (Path(tmp) / "highlight-m00-c00.mp4").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
