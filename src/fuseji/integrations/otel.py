"""OpenTelemetry SDK との統合ヘルパ (#161).

OTel の ``SpanProcessor.on_end`` は ``ReadableSpan`` を受け取るが、ReadableSpan には
``set_attribute`` が存在せず属性 mutation はできない。属性 mutation には
内部 ``_attributes`` (``BoundedAttributes``) を private API として叩く必要があり、
SDK バージョンアップで壊れる脆い経路となる。

本モジュールは「**属性を set する前にマスクする**」明示的なヘルパを提供する。
OTel SDK のどのバージョンでも動作し、ベンダーロックインもない。
v0.3 で example として導入 (#129) したものを公式 API に昇格 (#161)。

`[otel]` extra でインストール:

```bash
pip install 'fuseji[otel]'
```

使い方:

```python
from opentelemetry import trace
from fuseji import Masker
from fuseji.integrations.otel import mask_attribute

masker = Masker()
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("llm-call") as span:
    user_prompt = "メール taro@example.com 宛て..."
    mask_attribute(span, "gen_ai.prompt", user_prompt, masker)
```

複数属性を一括マスクするときは ``mask_attributes(span, mapping, masker)``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..engine import Masker

if TYPE_CHECKING:
    from opentelemetry.trace import Span

# マスク対象の典型 attribute key (gen_ai semantic conventions と派生)。
# Langfuse / Phoenix / OpenInference / OpenLIT 等の主要フレームワークが採用する
# 命名を網羅する。利用者は `mask_attributes(..., keys=...)` で上書き可能。
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
    """``span.set_attribute(key, value)`` の前に value をマスクする (#161).

    Args:
        span: OTel の ``Span`` (``set_attribute`` を持つアクティブな Span)
        key: 属性キー
        value: マスク対象の値。``str`` 以外 (``int`` / ``bool`` / ``Sequence``
            等) はそのまま ``set_attribute`` する
        masker: 使用する ``Masker`` インスタンス。``None`` のとき新規構築
            (パフォーマンス上は呼び出し側で 1 つ作って使い回すことを推奨)
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
    """複数 attribute を一括で set。``keys`` で対象キーを絞れる (#161).

    Args:
        span: OTel ``Span``
        attributes: ``key → value`` の Mapping
        masker: 使用する ``Masker``。``None`` で新規構築
        keys: マスク対象に含めるキーの tuple。``None`` のとき
            ``DEFAULT_ATTRIBUTE_KEYS`` を使う。空 tuple ``()`` は
            「フィルタなし」を意味し、すべての文字列属性をマスク対象にする
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


__all__ = [
    "DEFAULT_ATTRIBUTE_KEYS",
    "mask_attribute",
    "mask_attributes",
]
