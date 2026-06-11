"""日本の電話番号認識器."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..entity_types import JP_PHONE_NUMBER
from ..types import Entity
from .base import normalize, regex_analyze

# 先頭 0 + 8〜10 桁 = 全 9〜11 桁。間に任意の `-` または空白を許容。
_PHONE_PATTERN = re.compile(r"0(?:[-\s]?\d){8,10}")


def _validate(digits: str) -> float | None:
    """numbering plan による検証。有効なら推定スコアを返す。"""
    n = len(digits)
    if n < 10 or n > 11 or not digits.startswith("0"):
        return None
    # 携帯: 070/080/090 + 8 桁
    if n == 11 and digits[:3] in ("070", "080", "090"):
        return 0.95
    # フリーダイヤル: 0120 + 6 or 7 桁
    if digits.startswith("0120") and n in (10, 11):
        return 0.95
    # ナビダイヤル: 0570 + 6 桁
    if digits.startswith("0570") and n == 10:
        return 0.95
    # 固定電話: 10 桁
    if n == 10:
        return 0.85
    return None


class JpPhoneRecognizer:
    """日本の電話番号認識器。

    携帯（070/080/090）、フリーダイヤル（0120）、ナビダイヤル（0570）、
    固定電話（10 桁）を検出。ハイフン・空白セパレーター、全角数字・
    全角ハイフンに対応。numbering plan による桁数・プレフィックス検証で
    偽陽性を抑制する。
    """

    entity_type = JP_PHONE_NUMBER
    name = "jp_phone"

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterable[Entity]:
        return regex_analyze(
            text,
            entity_type=self.entity_type,
            recognizer_name=self.name,
            pattern=_PHONE_PATTERN,
            validate=_validate,
            normalize_fn=normalize,
            normalized=normalized,
            require_digit_boundary=True,
            strip_separators_before_validate=True,
        )
