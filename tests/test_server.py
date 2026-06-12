"""server/app.py のテスト（fastapi が必要）."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from fuseji.server.app import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestHealthz:
    def test_healthz_は_200_ok(self, client: TestClient) -> None:
        res = client.get("/healthz")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestMaskEndpoint:
    def test_str_を_mask(self, client: TestClient) -> None:
        res = client.post("/mask", json={"data": "メール: taro@example.com"})
        assert res.status_code == 200
        body = res.json()
        assert "<EMAIL_1>" in body["data"]

    def test_dict_を_mask(self, client: TestClient) -> None:
        res = client.post("/mask", json={"data": {"email": "a@b.com", "name": "山田"}})
        assert res.status_code == 200
        body = res.json()
        assert "<EMAIL_1>" in body["data"]["email"]
        assert body["data"]["name"] == "山田"

    def test_list_を_mask(self, client: TestClient) -> None:
        res = client.post("/mask", json={"data": ["a@b.com", "c@d.com"]})
        assert res.status_code == 200
        body = res.json()
        assert all("<EMAIL_" in s for s in body["data"])

    def test_PII_なしは素通し(self, client: TestClient) -> None:
        res = client.post("/mask", json={"data": "hello world"})
        assert res.status_code == 200
        assert res.json()["data"] == "hello world"

    def test_非対象型は素通し(self, client: TestClient) -> None:
        res = client.post("/mask", json={"data": {"n": 42, "b": True, "x": None}})
        assert res.status_code == 200
        assert res.json()["data"] == {"n": 42, "b": True, "x": None}


class TestDetectEndpoint:
    def test_entity_を返す_デフォルトでは_text_は_None(self, client: TestClient) -> None:
        # #143: デフォルトで原 PII surface は返さない
        res = client.post("/detect", json={"text": "メール: taro@example.com"})
        assert res.status_code == 200
        body = res.json()
        assert len(body["entities"]) == 1
        e = body["entities"][0]
        assert e["type"] == "EMAIL"
        assert e["text"] is None
        # オフセット系メタは残る
        assert "start" in e
        assert "end" in e
        assert "score" in e
        assert "recognizer" in e

    def test_検出ゼロは空リスト(self, client: TestClient) -> None:
        res = client.post("/detect", json={"text": "PII なし"})
        assert res.status_code == 200
        assert res.json()["entities"] == []

    def test_複数_entity(self, client: TestClient) -> None:
        res = client.post(
            "/detect",
            json={"text": "a@b.com と 090-1234-5678"},
        )
        body = res.json()
        types = {e["type"] for e in body["entities"]}
        assert "EMAIL" in types
        assert "JP_PHONE_NUMBER" in types

    def test_text_欠落は_422(self, client: TestClient) -> None:
        res = client.post("/detect", json={})
        assert res.status_code == 422


class TestDetectIncludeSurface:
    """#143: detect_include_surface opt-in 挙動."""

    def test_opt_in_すると_原_surface_が_含まれる(self) -> None:
        from fuseji.server.app import create_app

        c = TestClient(create_app(detect_include_surface=True))
        res = c.post("/detect", json={"text": "メール: taro@example.com"})
        body = res.json()
        e = body["entities"][0]
        assert e["type"] == "EMAIL"
        assert e["text"] == "taro@example.com"

    def test_opt_in_でも_高センシティビティ_type_は_redacted(self) -> None:
        from fuseji.server.app import create_app

        c = TestClient(create_app(detect_include_surface=True))
        # MY_NUMBER 12 桁 (チェックディジット適合する公開サンプル)
        res = c.post("/detect", json={"text": "個人番号 123456789018 です"})
        body = res.json()
        my_number_entities = [e for e in body["entities"] if e["type"] == "MY_NUMBER"]
        assert len(my_number_entities) == 1
        assert my_number_entities[0]["text"] == "<redacted>"

    def test_opt_in_でも_credit_card_は_redacted(self) -> None:
        from fuseji.server.app import create_app

        c = TestClient(create_app(detect_include_surface=True))
        # Visa test number (Luhn 適合)
        res = c.post("/detect", json={"text": "card: 4242-4242-4242-4242"})
        body = res.json()
        cc_entities = [e for e in body["entities"] if e["type"] == "CREDIT_CARD"]
        assert len(cc_entities) == 1
        assert cc_entities[0]["text"] == "<redacted>"

    def test_env_var_で_opt_in_できる(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fuseji.server.app import create_app

        monkeypatch.setenv("FUSEJI_DETECT_INCLUDE_SURFACE", "1")
        c = TestClient(create_app())
        res = c.post("/detect", json={"text": "メール: taro@example.com"})
        e = res.json()["entities"][0]
        assert e["text"] == "taro@example.com"

    def test_デフォルト_OpenAPI_スキーマでも_text_は_optional(self, client: TestClient) -> None:
        # OpenAPI で text が nullable / optional になっていること
        res = client.get("/openapi.json")
        schema = res.json()
        entity_schema = schema["components"]["schemas"]["EntityModel"]
        # text は required から除外、または nullable
        text_prop = entity_schema["properties"]["text"]
        required = entity_schema.get("required", [])
        # text は required ではない、もしくは nullable=True
        text_repr = str(text_prop.get("anyOf", text_prop.get("type", "")))
        assert "text" not in required or "null" in text_repr


class TestOpenAPI:
    def test_openapi_スキーマが取得できる(self, client: TestClient) -> None:
        res = client.get("/openapi.json")
        assert res.status_code == 200
        paths = res.json()["paths"]
        assert "/mask" in paths
        assert "/detect" in paths
        assert "/healthz" in paths

    def test_openapi_version_は___version___と一致する(self, client: TestClient) -> None:
        # ハードコード文字列ではなく fuseji.__version__ が反映されることを確認
        from fuseji import __version__

        res = client.get("/openapi.json")
        assert res.json()["info"]["version"] == __version__


class TestLifespanWarmup:
    """#173: FastAPI lifespan で Masker をウォームアップ."""

    def test_TestClient_with_経由で_lifespan_が_実行される(self) -> None:
        # TestClient(app) はデフォルトで lifespan を起動する (httpx の挙動)。
        # ウォームアップ中に例外が出ないこと、ヘルスチェックが lifespan 完了後に
        # 200 を返すことを検証する。
        from fuseji.server.app import create_app

        with TestClient(create_app()) as c:
            res = c.get("/healthz")
            assert res.status_code == 200

    def test_warmup_後に_最初の_mask_が_失敗しない(self) -> None:
        # lifespan 内で actual_masker.mask("warmup ...") を 1 回呼ぶため、
        # 認識器コンパイル等の初期化が startup 時に完了している。
        # ここでは「lifespan 内で例外が出るとリクエストが受け付けられなくなる」
        # 経路の回帰防止として、最初の /mask が即座に 200 を返すことを確認。
        from fuseji.server.app import create_app

        with TestClient(create_app()) as c:
            res = c.post("/mask", json={"data": "first request taro@example.com"})
            assert res.status_code == 200
            assert "taro@example.com" not in res.json()["data"]


class TestBodySizeLimit:
    def test_デフォルト_1MB_未満は受け付ける(self, client: TestClient) -> None:
        small = {"data": "a" * 100}
        res = client.post("/mask", json=small)
        assert res.status_code == 200

    def test_デフォルト_1MB_超は_413(self, client: TestClient) -> None:
        # Content-Length が 2MB を示すよう、十分大きな string を投げる
        big = {"data": "a" * 2_000_000}
        res = client.post("/mask", json=big)
        assert res.status_code == 413
        assert res.json()["detail"] == "payload too large"

    def test_chunked_でも上限を超えれば_413(self) -> None:
        """Content-Length を欠いた chunked リクエストでも上限が効く (#87).

        小さい max_bytes に絞り、TestClient 経由で大きいデータを送る。
        TestClient は通常 Content-Length を付けるため、Content-Length ヘッダを
        明示的に削除した状況のシミュレーションは httpx の制約で難しい。
        ここでは max_bytes を 50 に絞り、累積バイト数判定が機能する経路を
        通すことで body stream を見るパスをカバーする。
        """
        from fuseji.server.app import create_app

        # max=50 で 200 バイトの body を送る → 413
        small_app = create_app(max_body_bytes=50)
        c = TestClient(small_app)
        res = c.post("/mask", json={"data": "a" * 200})
        assert res.status_code == 413
        assert res.json()["detail"] == "payload too large"

    def test_ASGI_middleware_直接呼び出しで_受信途中で打ち切る(self) -> None:
        """pure ASGI 経路で、Content-Length 未宣言かつ累積で上限超過するケース."""
        import asyncio
        import json
        from typing import Any

        from fuseji.server.app import BodySizeLimitMiddleware

        # ダミー ASGI アプリ（呼ばれたら 200 OK を返す）
        called: dict[str, bool] = {"app_called": False}

        async def dummy_app(scope: object, receive: object, send: Any) -> None:
            called["app_called"] = True
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = BodySizeLimitMiddleware(dummy_app, max_bytes=10)

        # 累積 30 バイトの chunked body を受信する receive を作る
        chunks = [
            {"type": "http.request", "body": b"a" * 5, "more_body": True},
            {"type": "http.request", "body": b"b" * 10, "more_body": True},
            {"type": "http.request", "body": b"c" * 15, "more_body": False},
        ]
        idx = {"i": 0}

        async def receive() -> dict[str, Any]:
            i = idx["i"]
            idx["i"] += 1
            return chunks[i]

        # send 内容を捕捉
        sent: list[dict[str, Any]] = []

        async def send(msg: dict[str, Any]) -> None:
            sent.append(msg)

        scope = {
            "type": "http",
            "headers": [],  # Content-Length なし
            "method": "POST",
            "path": "/mask",
        }
        asyncio.run(middleware(scope, receive, send))

        # 下流アプリは呼ばれなかった
        assert called["app_called"] is False
        # 413 が返った
        assert any(m["type"] == "http.response.start" and m["status"] == 413 for m in sent)
        body_msgs = [m for m in sent if m["type"] == "http.response.body"]
        assert len(body_msgs) == 1
        assert json.loads(body_msgs[0]["body"])["detail"] == "payload too large"


class TestCreateAppFactory:
    def test_create_app_でカスタム_masker_を注入できる(self) -> None:
        """create_app(masker=...) で DI が機能することを確認."""
        from fuseji import Masker
        from fuseji.server.app import create_app

        # threshold を極端に高くして何も検出しない Masker を作る
        custom = Masker(threshold=1.5)
        custom_app = create_app(masker=custom)
        c = TestClient(custom_app)
        res = c.post("/mask", json={"data": "a@b.com"})
        assert res.status_code == 200
        # カスタム Masker が使われ、EMAIL は検出されずに素通し
        assert res.json()["data"] == "a@b.com"

    def test_create_app_でカスタム_max_body_bytes_を指定できる(self) -> None:
        from fuseji.server.app import create_app

        # 100 バイト上限の小さな app を作る
        small_app = create_app(max_body_bytes=100)
        c = TestClient(small_app)
        big = {"data": "a" * 1000}
        res = c.post("/mask", json=big)
        assert res.status_code == 413

    def test_モジュールスコープ_app_は_create_app_と独立(self) -> None:
        """既定の `app` モジュール変数も後方互換で動作する."""
        from fuseji.server.app import app, create_app

        custom_app = create_app()
        # 異なるインスタンスだが同じ動作
        assert app is not custom_app
        c1 = TestClient(app)
        c2 = TestClient(custom_app)
        assert c1.get("/healthz").json() == c2.get("/healthz").json() == {"status": "ok"}


class TestRequestTimeout:
    """RequestTimeoutMiddleware の挙動 (#29)."""

    def test_デフォルト_30s_では通常リクエストが通る(self, client: TestClient) -> None:
        # 既定 30s 内で完了する軽量リクエスト
        res = client.post("/mask", json={"data": "hello"})
        assert res.status_code == 200

    def test_タイムアウト超過で_504_を返す(self) -> None:
        """マスカーをスタブ化し、確実に timeout 発火する状況を作る."""
        import time

        from fuseji import Masker
        from fuseji.server.app import create_app

        class _SlowMasker:
            """50ms スリープしてからマスクするスタブ。"""

            def __init__(self) -> None:
                self._inner = Masker()

            def mask_json(self, data: object) -> object:
                time.sleep(0.05)
                return self._inner.mask_json(data)

            def detect(self, text: str) -> object:
                time.sleep(0.05)
                return self._inner.detect(text)

        # 1ms タイムアウトで確実に超過させる
        slow_app = create_app(masker=_SlowMasker(), timeout_seconds=0.001)  # type: ignore[arg-type]
        c = TestClient(slow_app)
        res = c.post("/mask", json={"data": "hello"})
        assert res.status_code == 504
        assert res.json()["detail"] == "request timeout"

    def test_create_app_でカスタム_timeout_seconds_を指定できる(self) -> None:
        from fuseji.server.app import create_app

        app_with_timeout = create_app(timeout_seconds=10.0)
        c = TestClient(app_with_timeout)
        res = c.get("/healthz")
        assert res.status_code == 200  # 通常リクエストは通る

    def test_環境変数で_timeout_を上書きできる(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fuseji.server.app import _timeout_seconds_from_env

        monkeypatch.setenv("FUSEJI_SERVER_TIMEOUT_SECONDS", "5.5")
        assert _timeout_seconds_from_env() == 5.5

    def test_不正な環境変数値はデフォルトにフォールバック(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fuseji.server.app import DEFAULT_TIMEOUT_SECONDS, _timeout_seconds_from_env

        monkeypatch.setenv("FUSEJI_SERVER_TIMEOUT_SECONDS", "not-a-number")
        assert _timeout_seconds_from_env() == DEFAULT_TIMEOUT_SECONDS

    def test_負の値はデフォルトにフォールバック(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fuseji.server.app import DEFAULT_TIMEOUT_SECONDS, _timeout_seconds_from_env

        monkeypatch.setenv("FUSEJI_SERVER_TIMEOUT_SECONDS", "-1")
        assert _timeout_seconds_from_env() == DEFAULT_TIMEOUT_SECONDS


class TestApiKeyAuth:
    """ApiKeyAuthMiddleware の挙動 (#83)."""

    def test_api_key_未設定なら_誰でも_mask_を叩ける(self, client: TestClient) -> None:
        # デフォルトの module-level `app` は API キー未設定（互換動作）
        res = client.post("/mask", json={"data": "hello"})
        assert res.status_code == 200

    def test_api_key_設定時_正しいヘッダで_200(self) -> None:
        from fuseji.server.app import create_app

        secured_app = create_app(api_key="s3cret")
        c = TestClient(secured_app)
        res = c.post("/mask", headers={"X-API-Key": "s3cret"}, json={"data": "hello"})
        assert res.status_code == 200

    def test_api_key_設定時_ヘッダなしで_401(self) -> None:
        from fuseji.server.app import create_app

        secured_app = create_app(api_key="s3cret")
        c = TestClient(secured_app)
        res = c.post("/mask", json={"data": "hello"})
        assert res.status_code == 401
        assert res.json()["detail"] == "unauthorized"
        # WWW-Authenticate ヘッダで認証スキームを明示
        assert "ApiKey" in res.headers.get("www-authenticate", "")

    def test_api_key_設定時_誤ったキーで_401(self) -> None:
        from fuseji.server.app import create_app

        secured_app = create_app(api_key="s3cret")
        c = TestClient(secured_app)
        res = c.post("/mask", headers={"X-API-Key": "wrong"}, json={"data": "hello"})
        assert res.status_code == 401

    def test_healthz_は_api_key_なしでも叩ける(self) -> None:
        from fuseji.server.app import create_app

        secured_app = create_app(api_key="s3cret")
        c = TestClient(secured_app)
        # /healthz は保護対象外（reverse-proxy / k8s liveness probe 想定）
        res = c.get("/healthz")
        assert res.status_code == 200

    def test_openapi_スキーマは_api_key_なしでも叩ける(self) -> None:
        from fuseji.server.app import create_app

        secured_app = create_app(api_key="s3cret")
        c = TestClient(secured_app)
        res = c.get("/openapi.json")
        assert res.status_code == 200

    def test_detect_も_api_key_で保護される(self) -> None:
        from fuseji.server.app import create_app

        secured_app = create_app(api_key="s3cret")
        c = TestClient(secured_app)
        # ヘッダなしは 401
        res1 = c.post("/detect", json={"text": "x"})
        assert res1.status_code == 401
        # 正しいヘッダで 200
        res2 = c.post("/detect", headers={"X-API-Key": "s3cret"}, json={"text": "x"})
        assert res2.status_code == 200

    def test_環境変数で_api_key_を上書きできる(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FUSEJI_API_KEY", "env-key")
        from fuseji.server.app import _api_key_from_env

        assert _api_key_from_env() == "env-key"

    def test_空文字列の_API_KEY_は無効として扱う(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FUSEJI_API_KEY", "   ")
        from fuseji.server.app import _api_key_from_env

        assert _api_key_from_env() is None


class TestCors:
    """CORS 制御 (#83)."""

    def test_cors_origins_未設定なら_CORS_ヘッダなし(self, client: TestClient) -> None:
        # デフォルト app は CORS 無効
        res = client.options(
            "/mask",
            headers={
                "Origin": "https://attacker.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        # CORS ヘッダが返らない（同一オリジンのみ許可される実質状態）
        assert "access-control-allow-origin" not in res.headers

    def test_cors_origins_設定時_許可オリジンには_ACAO_ヘッダ(self) -> None:
        from fuseji.server.app import create_app

        cors_app = create_app(cors_origins=["https://app.example.com"])
        c = TestClient(cors_app)
        res = c.options(
            "/mask",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert res.headers.get("access-control-allow-origin") == "https://app.example.com"

    def test_cors_origins_未許可オリジンには_ACAO_なし(self) -> None:
        from fuseji.server.app import create_app

        cors_app = create_app(cors_origins=["https://app.example.com"])
        c = TestClient(cors_app)
        res = c.options(
            "/mask",
            headers={
                "Origin": "https://attacker.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        # 未許可オリジンへの ACAO は返さない
        assert res.headers.get("access-control-allow-origin") != "https://attacker.example.com"

    def test_環境変数で_CORS_origins_をカンマ区切りで上書き(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FUSEJI_CORS_ORIGINS", "https://a.example.com, https://b.example.com")
        from fuseji.server.app import _cors_origins_from_env

        assert _cors_origins_from_env() == ["https://a.example.com", "https://b.example.com"]
