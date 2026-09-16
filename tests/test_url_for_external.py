"""External URL generation behind path-prefixed reverse proxies.

Covers ``request.url_for`` with trusted proxy headers and ``app.url_for``
with an explicitly configured public base URL.
"""

import pytest

from sanic import Sanic
from sanic.exceptions import URLBuildError
from sanic.response import text


XFF = {"X-Forwarded-For": "203.0.113.9"}


@pytest.fixture
def proxied_app(app: Sanic) -> Sanic:
    app.config.PROXIES_COUNT = 1

    @app.get("/hi", name="hi")
    async def hi(request):
        return text(request.url_for("hi"))

    @app.get("/item/<pk:int>", name="item")
    async def item(request, pk):
        return text(request.url_for("item", pk=pk, q="1"))

    @app.get("/override", name="override")
    async def override(request):
        return text(
            request.url_for("hi", _server="other.org", _scheme="http")
        )

    @app.websocket("/ws", name="ws")
    async def ws(request, ws_conn):
        pass

    @app.get("/wsurl", name="wsurl")
    async def wsurl(request):
        return text(request.url_for("ws"))

    return app


# --- request.url_for + X-Forwarded-* -----------------------------------


def test_forwarded_path_prefix_is_applied(proxied_app):
    _, response = proxied_app.test_client.get(
        "/hi",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Path": "/api/hi",
        },
    )
    assert response.text == "https://example.com/api/hi"


def test_forwarded_prefix_with_port_params_and_query(proxied_app):
    _, response = proxied_app.test_client.get(
        "/item/5",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "8443",
            "X-Forwarded-Path": "/api/item/5",
        },
    )
    assert response.text == "https://example.com:8443/api/item/5?q=1"


def test_forwarded_default_port_is_omitted(proxied_app):
    _, response = proxied_app.test_client.get(
        "/hi",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Port": "443",
            "X-Forwarded-Path": "/api/hi",
        },
    )
    assert response.text == "https://example.com/api/hi"


def test_forwarded_nested_prefix(proxied_app):
    _, response = proxied_app.test_client.get(
        "/hi",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Path": "/api/v1/hi",
        },
    )
    assert response.text == "https://example.com/api/v1/hi"


def test_forwarded_path_without_prefix_is_unchanged(proxied_app):
    _, response = proxied_app.test_client.get(
        "/hi",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Path": "/hi",
        },
    )
    assert response.text == "https://example.com/hi"


def test_forwarded_prefix_with_trailing_slash_has_no_double_slash(
    proxied_app,
):
    _, response = proxied_app.test_client.get(
        "/hi",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Path": "/api//hi",
        },
    )
    assert response.text == "https://example.com/api/hi"


def test_forwarded_websocket_uses_wss(proxied_app):
    _, response = proxied_app.test_client.get(
        "/wsurl",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Path": "/api/wsurl",
        },
    )
    assert response.text == "wss://example.com/api/ws"


def test_explicit_kwargs_override_forwarded(proxied_app):
    _, response = proxied_app.test_client.get(
        "/override",
        headers={
            **XFF,
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Path": "/api/override",
        },
    )
    assert response.text == "http://other.org/hi"


def test_untrusted_proxy_headers_are_ignored(app):
    # No PROXIES_COUNT / REAL_IP_HEADER configured: headers must be ignored.
    @app.get("/hi", name="hi")
    async def hi(request):
        return text(request.url_for("hi"))

    request, response = app.test_client.get(
        "/hi",
        headers={
            **XFF,
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Path": "/pwned/hi",
        },
    )
    assert response.text == f"http://{request.host}/hi"
    assert "evil.example" not in response.text
    assert "/pwned" not in response.text


# --- request.url_for + RFC 7239 Forwarded --------------------------------


def test_rfc7239_forwarded_path_prefix(proxied_app):
    proxied_app.config.FORWARDED_SECRET = "mySecret"
    _, response = proxied_app.test_client.get(
        "/hi",
        headers={
            "Forwarded": (
                "for=203.0.113.9;proto=https;host=example.com;"
                'path="/api/hi";secret=mySecret'
            ),
        },
    )
    assert response.text == "https://example.com/api/hi"


# --- app.url_for + configured public base URL ----------------------------


def test_external_base_url_is_used_without_request(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    app.config.EXTERNAL_BASE_URL = "https://example.com/api"
    assert app.url_for("hi", _external=True) == "https://example.com/api/hi"


def test_external_base_url_trailing_slash(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    app.config.EXTERNAL_BASE_URL = "https://example.com/api/"
    assert app.url_for("hi", _external=True) == "https://example.com/api/hi"


def test_external_base_url_with_port_and_params(app):
    @app.get("/item/<pk:int>", name="item")
    async def item(request, pk):
        pass

    app.config.EXTERNAL_BASE_URL = "https://example.com:8443/api"
    assert (
        app.url_for("item", pk=7, _external=True, q="x")
        == "https://example.com:8443/api/item/7?q=x"
    )


def test_external_base_url_precedes_server_name(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    app.config.SERVER_NAME = "https://old.example/legacy"
    app.config.EXTERNAL_BASE_URL = "https://example.com/api"
    assert app.url_for("hi", _external=True) == "https://example.com/api/hi"


def test_external_base_url_websocket_scheme(app):
    @app.websocket("/ws", name="ws")
    async def ws(request, ws_conn):
        pass

    app.config.EXTERNAL_BASE_URL = "https://example.com/api"
    assert app.url_for("ws", _external=True) == "wss://example.com/api/ws"


def test_explicit_server_overrides_external_base_url(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    app.config.EXTERNAL_BASE_URL = "https://example.com/api"
    assert (
        app.url_for("hi", _external=True, _server="other.org")
        == "http://other.org/hi"
    )


def test_external_base_url_used_by_request_url_for(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        return text(request.url_for("hi"))

    app.config.EXTERNAL_BASE_URL = "https://example.com/api"
    _, response = app.test_client.get("/hi")
    assert response.text == "https://example.com/api/hi"


def test_server_name_with_trailing_slash_has_no_double_slash(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    app.config.SERVER_NAME = "https://example.com/fnord/"
    assert app.url_for("hi", _external=True) == "https://example.com/fnord/hi"


def test_server_name_with_path_still_works(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    app.config.SERVER_NAME = "https://example.com:2342/fnord"
    assert (
        app.url_for("hi", _external=True)
        == "https://example.com:2342/fnord/hi"
    )


def test_external_without_any_base_raises(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    with pytest.raises(URLBuildError):
        app.url_for("hi", _external=True)


def test_internal_url_unaffected_by_external_base_url(app):
    @app.get("/hi", name="hi")
    async def hi(request):
        pass

    app.config.EXTERNAL_BASE_URL = "https://example.com/api"
    assert app.url_for("hi") == "/hi"
