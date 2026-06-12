"""`fuseji.integrations.otel` のテスト (#161, `[otel]` extra 必須)."""

from __future__ import annotations

from typing import Any

import pytest

# opentelemetry-api 未インストールの環境ではスキップ。
pytest.importorskip("opentelemetry.trace", reason="opentelemetry-api required for #161")

from fuseji import Masker
from fuseji.integrations.otel import (
    DEFAULT_ATTRIBUTE_KEYS,
    mask_attribute,
    mask_attributes,
)


class _FakeSpan:
    """`Span.set_attribute(key, value)` のみを記録する軽量フェイク.

    fuseji 側のロジック検証が目的なので、本物の OTel Span を作る必要はない。
    """

    def __init__(self) -> None:
        self.attributes: dict[str, Any] = {}

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class TestMaskAttribute:
    def test_文字列_value_は_マスクされて_set_される(self) -> None:
        span = _FakeSpan()
        mask_attribute(span, "gen_ai.prompt", "メール taro@example.com まで", Masker())
        out = span.attributes["gen_ai.prompt"]
        assert "taro@example.com" not in out
        assert "<EMAIL_1>" in out

    def test_非文字列_value_は_素通しで_set(self) -> None:
        span = _FakeSpan()
        mask_attribute(span, "llm.token_count", 42, Masker())
        assert span.attributes["llm.token_count"] == 42

    def test_bool_も_素通し(self) -> None:
        span = _FakeSpan()
        mask_attribute(span, "ok", True, Masker())
        assert span.attributes["ok"] is True

    def test_masker_省略時は_デフォルト構築(self) -> None:
        # masker=None でも例外なく動くこと
        span = _FakeSpan()
        mask_attribute(span, "gen_ai.prompt", "メール taro@example.com")
        assert "taro@example.com" not in span.attributes["gen_ai.prompt"]

    def test_PII_含まない文字列も_set_される(self) -> None:
        span = _FakeSpan()
        mask_attribute(span, "input.value", "PII なしのテキスト", Masker())
        # マスク結果は元と同じ（変更されないが set はされる）
        assert span.attributes["input.value"] == "PII なしのテキスト"


class TestMaskAttributes:
    def test_デフォルト_keys_対象だけ_マスク_他は_素通し(self) -> None:
        span = _FakeSpan()
        mask_attributes(
            span,
            {
                "gen_ai.prompt": "メール taro@example.com",
                "model": "gpt-5",  # 対象外 key → 素通し
            },
            Masker(),
        )
        assert "taro@example.com" not in span.attributes["gen_ai.prompt"]
        assert span.attributes["model"] == "gpt-5"

    def test_keys_引数で_対象を_絞れる(self) -> None:
        span = _FakeSpan()
        mask_attributes(
            span,
            {
                "custom.key": "メール taro@example.com",
                "gen_ai.prompt": "もう一つの PII xxx@example.com",
            },
            Masker(),
            keys=("custom.key",),
        )
        # custom.key は対象 → マスクされる
        assert "taro@example.com" not in span.attributes["custom.key"]
        # gen_ai.prompt は対象外 (keys に含まれない) → 素通し
        assert "xxx@example.com" in span.attributes["gen_ai.prompt"]

    def test_空_keys_tuple_は_フィルタなし_全件マスク対象(self) -> None:
        # keys=() (空 tuple) は「フィルタなし」を意味し、任意の key が対象
        span = _FakeSpan()
        mask_attributes(
            span,
            {"custom.x": "メール taro@example.com"},
            Masker(),
            keys=(),
        )
        # custom.x も対象になりマスクされる
        assert "taro@example.com" not in span.attributes["custom.x"]

    def test_非文字列_value_は_素通し(self) -> None:
        span = _FakeSpan()
        mask_attributes(
            span,
            {"gen_ai.prompt": 42},  # 対象 key だが値が非 str
            Masker(),
        )
        assert span.attributes["gen_ai.prompt"] == 42

    def test_DEFAULT_ATTRIBUTE_KEYS_に_主要_keys_が_含まれる(self) -> None:
        assert "gen_ai.prompt" in DEFAULT_ATTRIBUTE_KEYS
        assert "gen_ai.completion" in DEFAULT_ATTRIBUTE_KEYS
        assert "input.value" in DEFAULT_ATTRIBUTE_KEYS
        assert "output.value" in DEFAULT_ATTRIBUTE_KEYS
