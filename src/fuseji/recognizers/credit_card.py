"""クレジットカード認識器（Luhn チェック付き）."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..entity_types import CREDIT_CARD
from ..types import Entity
from .base import normalize, regex_analyze

# 13-19 桁の数字、間に任意のハイフン or 空白を許容
_CC_PATTERN = re.compile(r"\d(?:[-\s]?\d){12,18}")


def _luhn(digits: str) -> bool:
    """Luhn チェックディジット検証。digits は数字のみ。"""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _validate(digits: str) -> float | None:
    """13-19 桁かつ Luhn 通過なら score=0.95、それ以外は None で除外."""
    if not 13 <= len(digits) <= 19:
        return None
    if not _luhn(digits):
        return None
    return 0.95


class CreditCardRecognizer:
    """クレジットカード番号認識器。

    13-19 桁の数字列（ハイフン/空白セパレーター可、全角数字・全角ハイフンも対応）を
    候補とし、Luhn 検証に通過したもののみ Entity として返す。
    Luhn 失敗は credit card ではないことが確実なので除外する（偽陽性抑制）。
    """

    entity_type = CREDIT_CARD
    name = "credit_card"

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterator[Entity]:
        return regex_analyze(
            text,
            entity_type=self.entity_type,
            recognizer_name=self.name,
            pattern=_CC_PATTERN,
            validate=_validate,
            normalize_fn=normalize,
            normalized=normalized,
            strip_separators_before_validate=True,
        )
