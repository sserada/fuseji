"""マイナンバー（個人番号）認識器."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..types import Entity
from .base import has_digit_boundary, normalize_digits

# マイナンバーは 12 桁、セパレーターは使用しないのが標準的
_MY_NUMBER_PATTERN = re.compile(r"\d{12}")


def _checksum(first_11_digits: str) -> int:
    """上位 11 桁から 12 桁目のチェックディジットを算出（総務省公開仕様）.

    右から 1 桁目を n=1, 順次 n を増やして 11 まで。
    Qn は n が 1-6 で n+1, 7-11 で n-5。
    R = (Σ Pn × Qn) mod 11。R <= 1 のとき 0, それ以外は 11 - R。
    """
    s = 0
    for n in range(1, 12):
        p = int(first_11_digits[11 - n])  # 右から n 番目
        q = n + 1 if n <= 6 else n - 5
        s += p * q
    r = s % 11
    return 0 if r <= 1 else 11 - r


def _is_valid_my_number(digits: str) -> bool:
    """12 桁数字列が有効なマイナンバーか検査."""
    if len(digits) != 12 or not digits.isdigit():
        return False
    return _checksum(digits[:11]) == int(digits[11])


class MyNumberRecognizer:
    """マイナンバー（個人番号）認識器。

    12 桁の数字列を候補とし、チェックディジットが一致すれば高スコア
    （0.95）、そうでなければ低スコア（0.5）で Entity を返す。番号法の
    法的リスクを踏まえ、recall を優先して pattern-only でも検出する。
    """

    entity_type = "MY_NUMBER"

    def analyze(self, text: str) -> Iterable[Entity]:
        normalized = normalize_digits(text)
        for m in _MY_NUMBER_PATTERN.finditer(normalized):
            start = m.start()
            end = m.end()
            # 直前・直後に数字がある場合は別 ID の一部の可能性が高いので除外
            if has_digit_boundary(normalized, start, end):
                continue
            score = 0.95 if _is_valid_my_number(m.group()) else 0.5
            yield Entity(
                type=self.entity_type,
                text=text[start:end],
                start=start,
                end=end,
                score=score,
                recognizer="my_number",
            )
