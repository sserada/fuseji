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
    def test_entity_を返す(self, client: TestClient) -> None:
        res = client.post("/detect", json={"text": "メール: taro@example.com"})
        assert res.status_code == 200
        body = res.json()
        assert len(body["entities"]) == 1
        e = body["entities"][0]
        assert e["type"] == "EMAIL"
        assert e["text"] == "taro@example.com"
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
