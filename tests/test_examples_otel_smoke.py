"""examples/otel/main.py 相当のスモークテスト (#171).

example が走ったときに mask_attribute が span 属性をマスクすることを
InMemorySpanExporter 経由で検証する。example 本体ファイルそのものを
subprocess で実行する形にはせず、同じシナリオを再現することで:

- OTel SDK のメジャー更新時に test が即時 fail
- `fuseji.integrations.otel` の API 変更時にも検知
- PII (taro@example.com / 090-1234-5678) が span attribute に残らないことを最終検証

を CI で恒常化する。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# otel-sdk は [otel] extra に含めていないため、CI の test-extras / dev 環境で
# 取れない場合は skip する (本テストは公式モジュールの動作 smoke が目的)。
pytest.importorskip("opentelemetry.sdk.trace", reason="opentelemetry-sdk required for smoke")

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fuseji import Masker
from fuseji.integrations.otel import mask_attribute


@pytest.fixture(scope="module")
def tracer_provider() -> TracerProvider:
    """モジュール全体で 1 つだけ TracerProvider を bind する.

    OTel SDK は `set_tracer_provider` を 2 回呼ぶと 2 回目以降 warning で
    無視されるため、テスト毎に新規 provider を作ろうとすると干渉する。
    モジュールスコープで 1 度だけ set し、各テストでは provider に SimpleSpanProcessor
    + 専用 InMemorySpanExporter を **追加** することで test 間を分離する。
    """
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    return provider


@pytest.fixture
def memory_exporter(tracer_provider: TracerProvider) -> Iterator[InMemorySpanExporter]:
    """test 毎の InMemorySpanExporter (使い終わったら span を clear)."""
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    tracer_provider.add_span_processor(processor)
    try:
        yield exporter
    finally:
        # span を捨てて exporter を独立化 (provider 自体は再利用)
        exporter.clear()


def test_example_otel_main_相当のフローで_PII_が_span_attribute_に_残らない(
    memory_exporter: InMemorySpanExporter,
) -> None:
    """examples/otel/main.py が実行されたときの想定挙動を再現."""
    masker = Masker()
    tracer = trace.get_tracer("fuseji-otel-smoke")

    with tracer.start_as_current_span("llm-call") as span:
        mask_attribute(
            span,
            "gen_ai.prompt",
            "メール taro@example.com 宛てに 090-1234-5678 から連絡してください。",
            masker,
        )
        mask_attribute(
            span,
            "gen_ai.completion",
            "承知しました。山田様にお伝えします。",
            masker,
        )

    spans = [s for s in memory_exporter.get_finished_spans() if s.name == "llm-call"]
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})

    prompt = attrs["gen_ai.prompt"]
    assert isinstance(prompt, str)
    # 原 PII が attribute に残らない (CWE-200 / 「detect, never retain」原則)
    assert "taro@example.com" not in prompt
    assert "090-1234-5678" not in prompt
    # マスク済み placeholder が含まれる
    assert "<EMAIL_1>" in prompt
    assert "<JP_PHONE_NUMBER_1>" in prompt

    completion = attrs["gen_ai.completion"]
    assert isinstance(completion, str)
    # PII を含まないテキストは中身が変わらない
    assert "承知しました" in completion


def test_mask_attribute_が_新規_Masker_自動構築でも_動作(
    memory_exporter: InMemorySpanExporter,
) -> None:
    """example で利用者が masker= を省略しても fail-safe に動くこと."""
    tracer = trace.get_tracer("fuseji-otel-smoke-no-masker")
    with tracer.start_as_current_span("no-masker") as span:
        mask_attribute(span, "input.value", "taro@example.com への連絡")
    spans = [s for s in memory_exporter.get_finished_spans() if s.name == "no-masker"]
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert "taro@example.com" not in attrs["input.value"]
