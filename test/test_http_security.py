"""HTTP/SSE 传输安全边界测试。"""

import pytest
from starlette.requests import Request
from starlette.responses import Response

from adb_mysql_mcp_server import server


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeApp:
    def __init__(self):
        self.middlewares = []

    def add_middleware(self, middleware):
        self.middlewares.append(middleware)


class FakeServer:
    def __init__(self, config):
        self.config = config

    async def serve(self):
        pass


def _patch_server_run(monkeypatch):
    captured = {}

    def fake_config(app, **kwargs):
        captured["app"] = app
        captured["config"] = kwargs
        return kwargs

    monkeypatch.setattr(server.mcp, "activate", lambda enabled_groups: captured.setdefault("enabled_groups", enabled_groups))
    monkeypatch.setattr(server.mcp, "sse_app", lambda: FakeApp())
    monkeypatch.setattr(server.mcp, "streamable_http_app", lambda: FakeApp())
    monkeypatch.setattr(server.uvicorn, "Config", fake_config)
    monkeypatch.setattr(server.uvicorn, "Server", FakeServer)
    monkeypatch.setattr(server.anyio, "run", lambda _serve: None)
    return captured


def test_http_transport_defaults_to_loopback_without_api_key(monkeypatch):
    captured = _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "sse")
    monkeypatch.delenv("SERVER_HOST", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    server.main("sql")

    assert captured["config"]["host"] == "127.0.0.1"
    assert captured["app"].middlewares == [server.VerifyHeaderMiddleware]


def test_public_sse_requires_api_key(monkeypatch):
    _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "sse")
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ValueError, match="API_KEY is required"):
        server.main("sql")


def test_public_streamable_http_requires_api_key(monkeypatch):
    _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "streamable-http")
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ValueError, match="API_KEY is required"):
        server.main("sql")


def test_public_http_with_sql_only_and_api_key_is_allowed(monkeypatch):
    captured = _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "sse")
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("API_KEY", "t" * 32)

    server.main("sql")

    assert captured["config"]["host"] == "0.0.0.0"


def test_public_http_rejects_short_api_key(monkeypatch):
    _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "sse")
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("API_KEY", "short-token")

    with pytest.raises(ValueError, match="at least 32 characters"):
        server.main("sql")


def test_stdio_openapi_is_allowed_when_requested(monkeypatch):
    captured = _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "stdio")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "sk")

    server.main("openapi")

    assert captured["enabled_groups"] == ["openapi"]


def test_stdio_openapi_is_disabled_without_credentials(monkeypatch):
    captured = _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "stdio")
    monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", raising=False)

    server.main("openapi,sql")

    assert captured["enabled_groups"] == ["sql"]


def test_public_http_openapi_with_api_key_is_allowed(monkeypatch):
    captured = _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "sse")
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("API_KEY", "t" * 32)
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "sk")

    server.main("openapi")

    assert captured["config"]["host"] == "0.0.0.0"
    assert captured["enabled_groups"] == ["openapi"]


def test_public_http_openapi_still_requires_api_key(monkeypatch):
    _patch_server_run(monkeypatch)
    monkeypatch.setenv("SERVER_TRANSPORT", "sse")
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "sk")
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ValueError, match="API_KEY is required"):
        server.main("openapi")


async def _call_verify_header_middleware(monkeypatch, authorization: str | None):
    monkeypatch.setenv("API_KEY", "test-token")
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": headers})
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return Response("OK")

    middleware = server.VerifyHeaderMiddleware(app=lambda _scope, _receive, _send: None)
    response = await middleware.dispatch(request, call_next)
    return response, called


@pytest.mark.anyio
async def test_api_key_requires_bearer_authorization(monkeypatch):
    response, called = await _call_verify_header_middleware(monkeypatch, "Token test-token")

    assert response.status_code == 401
    assert called is False


@pytest.mark.anyio
async def test_api_key_accepts_bearer_authorization(monkeypatch):
    response, called = await _call_verify_header_middleware(monkeypatch, "Bearer test-token")

    assert response.status_code == 200
    assert called is True
