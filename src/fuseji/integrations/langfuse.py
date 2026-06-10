"""Langfuse SDK の mask フック用アダプター."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..engine import Masker

logger = logging.getLogger(__name__)

# 例外時に返す fail-closed なプレースホルダー
_FAIL_PLACEHOLDER = "[fuseji: masking failed]"


def make_mask_fn(masker: Masker | None = None) -> Callable[[Any], Any]:
    """Langfuse SDK の ``mask`` パラメータに渡せるマスキング関数を生成する。

    Args:
        masker: 使用する Masker インスタンス。``None`` のとき新規に
            ``Masker()`` を作る（v0.1 デフォルト認識器セット + Placeholder 戦略）。

    Returns:
        Langfuse SDK の ``mask=`` に渡せる callable。任意のデータ構造
        （str / dict / list / tuple 等）を受け取り、マスク済みの同型
        データを返す。

    例外ハンドリング:
        マスキング処理が例外で失敗した場合は fail-closed の方針で
        ``"[fuseji: masking failed]"`` 文字列を返す。PII 漏洩を避けるため
        原データはそのまま返さない。例外内容は WARN ログに記録する。

    使い方:
        >>> from langfuse import Langfuse
        >>> from fuseji.integrations.langfuse import make_mask_fn
        >>> langfuse = Langfuse(mask=make_mask_fn())
    """
    actual_masker: Masker = masker if masker is not None else Masker()

    def _mask(data: Any) -> Any:
        try:
            return actual_masker.mask_json(data)
        except Exception:
            logger.exception("fuseji: マスキング処理が例外で失敗")
            return _FAIL_PLACEHOLDER

    return _mask
