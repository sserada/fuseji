"""OpenTelemetry SDK + fuseji の最短サンプル (#129).

`mask_attribute()` で gen_ai.* 属性を set する前にマスクし、span 全体を
コンソール export する。

事前準備:
```bash
pip install -r requirements.txt
```

実行:
```bash
python main.py
```

期待出力（コンソール export 内 attributes セクション）:
- gen_ai.prompt: マスク済み（例: "メール <EMAIL_1> 宛てに <JP_PHONE_NUMBER_1> から..."）
- gen_ai.completion: 平文（PII なし）
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

from fuseji import Masker
from fuseji.integrations.otel import mask_attribute


def main() -> None:
    # TracerProvider をセットアップ
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    # Masker は 1 度だけ生成して使い回す
    masker = Masker()
    tracer = trace.get_tracer("fuseji-otel-example")

    with tracer.start_as_current_span("llm-call") as span:
        # 通常の set_attribute の代わりに mask_attribute を使うだけ
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

    provider.force_flush()


if __name__ == "__main__":
    main()
