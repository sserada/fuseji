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
