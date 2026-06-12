"""fuseji を OpenTelemetry SDK と組み合わせる helper (#129).

OTel の `SpanProcessor.on_end` は `ReadableSpan` を受け取るが、ReadableSpan には
`set_attribute` が存在せず属性 mutation はできない。属性 mutation には
内部 `_attributes`（BoundedAttributes）を private API として叩く必要があり、
SDK バージョンアップで壊れる脆い経路となる。

代わりに本サンプルでは **「属性を set する前にマスクする」明示的な helper** を
提供する。OTel SDK のどのバージョンでも動作し、ベンダーロックインもない。

使い方:

```python
from opentelemetry import trace
from fuseji import Masker
from mask_processor import mask_attribute

masker = Masker()
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("llm-call") as span:
    user_prompt = "メール taro@example.com 宛て..."
    mask_attribute(span, "gen_ai.prompt", user_prompt, masker)
    # ↑ 中で `masker.mask(user_prompt).text` で得たマスク済み値を set_attribute
```

複数の属性を一括マスクしたい場合は `mask_attributes(span, mapping, masker)` を使う。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opentelemetry.trace import Span

from fuseji import Masker

# マスク対象の典型 attribute key（gen_ai semantic conventions と派生）
DEFAULT_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.request.messages",
    "gen_ai.response.text",
    "llm.prompts",
    "llm.completions",
    "input.value",
    "output.value",
)


def mask_attribute(
    span: Span,
    key: str,
    value: Any,
    masker: Masker | None = None,
) -> None:
    """`span.set_attribute(key, value)` の前に value をマスクする。

    value が str 以外（int / bool / Sequence など）の場合はそのまま set_attribute。
    `masker=None` のときは新規 `Masker()` を生成する（推奨は呼び出し側で 1 つ作って
    使い回す）。
    """
    if isinstance(value, str):
        m = masker if masker is not None else Masker()
        value = m.mask(value).text
    span.set_attribute(key, value)


def mask_attributes(
    span: Span,
    attributes: Mapping[str, Any],
    masker: Masker | None = None,
    keys: tuple[str, ...] | None = None,
) -> None:
    """複数の attribute を一括で set。`keys` で対象 key を絞れる（デフォルトは全部）.

    Args:
        span: OTel Span（`set_attribute` を持つアクティブな Span）
        attributes: key → value の Mapping。
        masker: 利用する Masker。`None` で `Masker()` を 1 度だけ生成
        keys: マスク対象キー。`None` で `DEFAULT_ATTRIBUTE_KEYS`、`()` で全 attribute
            キーをマスク対象に。
    """
    m = masker if masker is not None else Masker()
    target_keys = keys if keys is not None else DEFAULT_ATTRIBUTE_KEYS
    for k, v in attributes.items():
        if target_keys and k not in target_keys:
            span.set_attribute(k, v)
            continue
        if isinstance(v, str):
            v = m.mask(v).text
        span.set_attribute(k, v)
