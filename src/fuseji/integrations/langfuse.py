"""Langfuse SDK の mask フック用アダプター."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from ..engine import Masker

logger = logging.getLogger(__name__)

# 例外時に返す fail-closed なプレースホルダー
_FAIL_PLACEHOLDER = "[fuseji: masking failed]"

# 環境変数で「フルトレースバックをログに出すか」を切り替える。デフォルトは
# off で、例外型名のみログする（PII を含むトレースバックを残さないため）。
# デバッグ目的で詳細が必要なときは FUSEJI_LANGFUSE_LOG_TRACEBACK=1 を設定する。
_LOG_TRACEBACK_ENV = "FUSEJI_LANGFUSE_LOG_TRACEBACK"


def _should_log_traceback() -> bool:
    return os.environ.get(_LOG_TRACEBACK_ENV, "0") == "1"


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
        原データはそのまま返さない。

        ログ出力は **デフォルトで例外型名のみ**（トレースバックなし）。
        トレースバックには元の PII を含む文字列が含まれる可能性があるため、
        ログ集約基盤への漏洩を防ぐ。デバッグ目的で完全なトレースバックが
        必要な場合は環境変数 ``FUSEJI_LANGFUSE_LOG_TRACEBACK=1`` を設定する。

    Example:
        Langfuse SDK と統合:

        >>> from langfuse import Langfuse  # doctest: +SKIP
        >>> from fuseji.integrations.langfuse import make_mask_fn
        >>> langfuse = Langfuse(mask=make_mask_fn())  # doctest: +SKIP

        スタンドアロンで動作確認:

        >>> from fuseji.integrations.langfuse import make_mask_fn
        >>> fn = make_mask_fn()
        >>> "<EMAIL_1>" in fn({"data": "メール a@b.com"})["data"]
        True
    """
    actual_masker: Masker = masker if masker is not None else Masker()

    def _mask(data: Any) -> Any:
        try:
            return actual_masker.mask_json(data)
        except Exception as e:
            if _should_log_traceback():
                logger.exception("fuseji: マスキング処理が例外で失敗")
            else:
                # デフォルト: 例外型のみログ。トレースバック内の PII 漏洩を防ぐ。
                logger.warning("fuseji: マスキング処理が例外で失敗 (%s)", type(e).__name__)
            return _FAIL_PLACEHOLDER

    return _mask
