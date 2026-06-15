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


class _ExplodingMasker:
    """``mask`` が常に例外を投げる Masker 互換オブジェクト (#222 fail-closed テスト用).

    Masker のサブクラスではなく duck typing で `.mask(text)` のみ提供する。
    """

    def mask(self, text: str) -> Any:
        raise RuntimeError(f"intentional failure for: {text}")


class _PartiallyExplodingMasker:
    """特定 substring を含む value のみ例外、それ以外は通常 mask (#222 部分失敗テスト).

    ``mask_attributes`` の属性ごと独立 fail-closed を検証するために、
    1 attribute だけ失敗させる用途。
    """

    def __init__(self, fail_marker: str) -> None:
        self._fail_marker = fail_marker
        self._delegate = Masker()

    def mask(self, text: str) -> Any:
        if self._fail_marker in text:
            raise RuntimeError(f"intentional partial failure: {text}")
        return self._delegate.mask(text)


class TestFailClosed:
    """#222: OTel adapter の fail-closed 経路.

    Masker.mask が例外を投げた場合に、原 value が span に流出せず、固定 placeholder
    が set されること、ログがデフォルトで例外型名のみであることを検証する。
    """

    _FAIL_PLACEHOLDER = "[fuseji: masking failed]"

    def test_mask_attribute_例外時に_原_value_は_span_に流出しない(self) -> None:
        span = _FakeSpan()
        # type: ignore[arg-type] — duck-typed Masker substitute
        mask_attribute(span, "gen_ai.prompt", "secret-pii", _ExplodingMasker())  # type: ignore[arg-type]
        assert span.attributes["gen_ai.prompt"] == self._FAIL_PLACEHOLDER
        # 原 value が偶発的に含まれていない
        assert "secret-pii" not in span.attributes["gen_ai.prompt"]

    def test_mask_attribute_例外時_デフォルトは_型名のみログ(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 環境変数を明示 unset (テスト並行実行時の他テスト副作用を防ぐ)
        monkeypatch.delenv("FUSEJI_OTEL_LOG_TRACEBACK", raising=False)
        span = _FakeSpan()
        with caplog.at_level("WARNING", logger="fuseji.integrations.otel"):
            mask_attribute(
                span,
                "gen_ai.prompt",
                "secret-pii",
                _ExplodingMasker(),  # type: ignore[arg-type]
            )
        # 例外型名はログされる
        assert any("RuntimeError" in r.getMessage() for r in caplog.records)
        # 原 value は traceback 抑制でログにも刻まれない
        assert not any("secret-pii" in r.getMessage() for r in caplog.records)

    def test_mask_attribute_traceback_env_有効時は_例外_traceback_出力(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FUSEJI_OTEL_LOG_TRACEBACK", "1")
        span = _FakeSpan()
        with caplog.at_level("ERROR", logger="fuseji.integrations.otel"):
            mask_attribute(
                span,
                "gen_ai.prompt",
                "any-value",
                _ExplodingMasker(),  # type: ignore[arg-type]
            )
        # logger.exception は ERROR レベルで traceback を含む
        assert any(r.exc_info is not None for r in caplog.records)

    def test_mask_attributes_属性ごとに_独立_fail_closed(self) -> None:
        """1 属性のマスク失敗が他属性の処理を止めないこと."""
        span = _FakeSpan()
        masker = _PartiallyExplodingMasker(fail_marker="FAIL_ME")
        mask_attributes(
            span,
            {
                "gen_ai.prompt": "メール taro@example.com",  # 正常マスク
                "gen_ai.completion": "FAIL_ME secret here",  # 例外
                "input.value": "PII なしのテキスト",  # 正常マスク (no-op)
            },
            masker,  # type: ignore[arg-type]
        )
        # 正常 mask されたものは元 PII が残らない
        assert "taro@example.com" not in span.attributes["gen_ai.prompt"]
        # 失敗した属性は固定 placeholder
        assert span.attributes["gen_ai.completion"] == self._FAIL_PLACEHOLDER
        assert "secret here" not in span.attributes["gen_ai.completion"]
        # 失敗の伝播で後続属性が止まっていないこと (PII なし入力は素通し)
        assert span.attributes["input.value"] == "PII なしのテキスト"

    def test_mask_attributes_全属性_例外でも_全属性に_placeholder_が_set_される(self) -> None:
        span = _FakeSpan()
        mask_attributes(
            span,
            {"gen_ai.prompt": "p1", "gen_ai.completion": "p2"},
            _ExplodingMasker(),  # type: ignore[arg-type]
        )
        assert span.attributes["gen_ai.prompt"] == self._FAIL_PLACEHOLDER
        assert span.attributes["gen_ai.completion"] == self._FAIL_PLACEHOLDER
