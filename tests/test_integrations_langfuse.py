"""integrations/langfuse.py のテスト（Langfuse SDK には依存しない）."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import pytest

from fuseji.engine import Masker
from fuseji.integrations.langfuse import make_mask_fn
from fuseji.types import Entity


class TestMakeMaskFn:
    def test_str_を_mask(self) -> None:
        fn = make_mask_fn()
        result = fn("メール: taro@example.com")
        assert isinstance(result, str)
        assert "<EMAIL_1>" in result

    def test_dict_を_mask(self) -> None:
        fn = make_mask_fn()
        result = fn({"email": "taro@example.com", "name": "山田"})
        assert "<EMAIL_1>" in result["email"]
        assert result["name"] == "山田"

    def test_list_を_mask(self) -> None:
        fn = make_mask_fn()
        result = fn(["a@b.com", "c@d.com"])
        assert all("<EMAIL_" in s for s in result)

    def test_ネスト構造を_mask(self) -> None:
        fn = make_mask_fn()
        data = {"trace": {"input": "電話 090-1234-5678"}, "tags": ["foo"]}
        result = fn(data)
        assert "<JP_PHONE_NUMBER_1>" in result["trace"]["input"]
        assert result["tags"] == ["foo"]

    def test_PII_を含まない値は素通し(self) -> None:
        fn = make_mask_fn()
        data = {"n": 42, "s": "hello"}
        assert fn(data) == data

    def test_カスタム_Masker_を渡せる(self) -> None:
        # 何も検出しないスタブ Masker を作る代わりに、threshold を高くする
        m = Masker(threshold=1.5)
        fn = make_mask_fn(m)
        # 通常検出される EMAIL も無効化される
        result = fn("a@b.com")
        assert result == "a@b.com"

    def test_デフォルトで_Masker_が使われる(self) -> None:
        # masker=None でも問題なく動作
        fn = make_mask_fn()
        result = fn("test")
        assert result == "test"

    def test_例外時は_fail_closed_な_placeholder(self, caplog: pytest.LogCaptureFixture) -> None:
        class _BrokenRecognizer:
            entity_type = "BROKEN"

            def analyze(self, text: str) -> Iterable[Entity]:
                raise RuntimeError("壊れた認識器")

        m = Masker(recognizers=[_BrokenRecognizer()])
        fn = make_mask_fn(m)

        with caplog.at_level(logging.WARNING):
            result = fn("どんな入力でも")

        assert result == "[fuseji: masking failed]"
        # WARN ログが記録される
        assert any("マスキング処理が例外" in r.message for r in caplog.records)

    def test_例外時にも原データを返さない(self) -> None:
        # PII 漏洩防止: 例外時は固定 placeholder で、原データは返らない
        class _BrokenRecognizer:
            entity_type = "BROKEN"

            def analyze(self, text: str) -> Iterable[Entity]:
                raise RuntimeError("壊れた認識器")

        m = Masker(recognizers=[_BrokenRecognizer()])
        fn = make_mask_fn(m)
        result: Any = fn("機密情報: secret@example.com")
        assert "secret" not in str(result)
        assert "example.com" not in str(result)
