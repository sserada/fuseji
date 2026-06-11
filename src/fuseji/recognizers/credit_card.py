"""クレジットカード認識器（Luhn チェック付き）."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..entity_types import CREDIT_CARD
from ..types import Entity
from .base import SEPARATOR_PATTERN, normalize

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


class CreditCardRecognizer:
    """クレジットカード番号認識器。

    13-19 桁の数字列（ハイフン/空白セパレーター可、全角数字・全角ハイフンも対応）を
    候補とし、Luhn 検証に通過したもののみ Entity として返す。
    Luhn 失敗は credit card ではないことが確実なので除外する（偽陽性抑制）。
    """

    entity_type = CREDIT_CARD

    def analyze(self, text: str) -> Iterable[Entity]:
        # 全角数字・全角ハイフンを正規化（1 文字 ↔ 1 文字なのでオフセット維持）
        normalized = normalize(text)
        for m in _CC_PATTERN.finditer(normalized):
            digits = SEPARATOR_PATTERN.sub("", m.group())
            if not 13 <= len(digits) <= 19:
                continue
            if not _luhn(digits):
                continue
            yield Entity(
                type=self.entity_type,
                text=text[m.start() : m.end()],  # 元テキストの表層を返す
                start=m.start(),
                end=m.end(),
                score=0.95,
                recognizer="credit_card",
            )
