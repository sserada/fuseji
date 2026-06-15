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

## fail-closed (#222)

``Masker.mask`` が例外を投げた場合は固定 placeholder ``"[fuseji: masking failed]"``
を ``set_attribute`` する。原 value を span に流出させない。``mask_attributes`` は
属性ごとに独立した try/except のため、ある属性のマスク失敗が他属性の処理を止めない。

トレースバックには原 PII を含む文字列が刻まれる可能性があるため、デフォルトでは
例外型名のみログする。詳細 traceback が必要なときは環境変数
``FUSEJI_OTEL_LOG_TRACEBACK=1`` を設定する。Langfuse adapter
(`FUSEJI_LANGFUSE_LOG_TRACEBACK`) と方針を統一。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..engine import Masker

if TYPE_CHECKING:
    from opentelemetry.trace import Span

logger = logging.getLogger(__name__)

# 例外時に span 属性へ書き込む fail-closed なプレースホルダー (Langfuse adapter と統一)
_FAIL_PLACEHOLDER = "[fuseji: masking failed]"

# 環境変数で「フルトレースバックをログに出すか」を切り替える。デフォルトは
# off で、例外型名のみログする（トレースバック内に PII を含む文字列が刻まれる
# 経路を遮断するため）。Langfuse adapter の FUSEJI_LANGFUSE_LOG_TRACEBACK と統一。
_LOG_TRACEBACK_ENV = "FUSEJI_OTEL_LOG_TRACEBACK"

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


def _should_log_traceback() -> bool:
    return os.environ.get(_LOG_TRACEBACK_ENV, "0") == "1"


def _safe_mask(masker: Masker, key: str, value: str) -> str:
    """``masker.mask(value).text`` を try/except でラップした fail-closed 版 (#222).

    例外時は固定 placeholder を返す。原 value は **絶対に返さない**。
    """
    try:
        return masker.mask(value).text
    except Exception as e:
        if _should_log_traceback():
            logger.exception("fuseji: OTel attribute マスキング処理が例外で失敗 (key=%s)", key)
        else:
            # デフォルト: 例外型のみログ。トレースバック内の PII 漏洩を防ぐ。
            logger.warning(
                "fuseji: OTel attribute マスキング処理が例外で失敗 (key=%s, %s)",
                key,
                type(e).__name__,
            )
        return _FAIL_PLACEHOLDER


def mask_attribute(
    span: Span,
    key: str,
    value: Any,
    masker: Masker | None = None,
) -> None:
    """``span.set_attribute(key, value)`` の前に value をマスクする (#161, #222).

    Args:
        span: OTel の ``Span`` (``set_attribute`` を持つアクティブな Span)
        key: 属性キー
        value: マスク対象の値。``str`` 以外 (``int`` / ``bool`` / ``Sequence``
            等) はそのまま ``set_attribute`` する
        masker: 使用する ``Masker`` インスタンス。``None`` のとき新規構築
            (パフォーマンス上は呼び出し側で 1 つ作って使い回すことを推奨)

    fail-closed: ``masker.mask`` が例外を投げた場合は固定 placeholder
    ``"[fuseji: masking failed]"`` を set し、原 value を span に流出させない。
    詳細は本モジュールの docstring を参照。
    """
    if isinstance(value, str):
        m = masker if masker is not None else Masker()
        value = _safe_mask(m, key, value)
    span.set_attribute(key, value)


def mask_attributes(
    span: Span,
    attributes: Mapping[str, Any],
    masker: Masker | None = None,
    keys: tuple[str, ...] | None = None,
) -> None:
    """複数 attribute を一括で set。``keys`` で対象キーを絞れる (#161, #222).

    Args:
        span: OTel ``Span``
        attributes: ``key → value`` の Mapping
        masker: 使用する ``Masker``。``None`` で新規構築
        keys: マスク対象に含めるキーの tuple。``None`` のとき
            ``DEFAULT_ATTRIBUTE_KEYS`` を使う。空 tuple ``()`` は
            「フィルタなし」を意味し、すべての文字列属性をマスク対象にする

    fail-closed: 属性ごとに独立した try/except (`_safe_mask` 経由) で、
    ある属性のマスク失敗が他属性の処理を止めない。失敗属性には固定 placeholder
    ``"[fuseji: masking failed]"`` が set される。
    """
    m = masker if masker is not None else Masker()
    target_keys = keys if keys is not None else DEFAULT_ATTRIBUTE_KEYS
    for k, v in attributes.items():
        if target_keys and k not in target_keys:
            span.set_attribute(k, v)
            continue
        if isinstance(v, str):
            v = _safe_mask(m, k, v)
        span.set_attribute(k, v)


__all__ = [
    "DEFAULT_ATTRIBUTE_KEYS",
    "mask_attribute",
    "mask_attributes",
]
