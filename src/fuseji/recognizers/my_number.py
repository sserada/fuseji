"""マイナンバー（個人番号）認識器."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..entity_types import MY_NUMBER
from ..types import Entity
from .base import normalize, regex_analyze

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


def _validate(digits: str) -> float | None:
    """チェックディジット一致なら 0.95、不一致でも 0.5 で採用（recall 優先）."""
    return 0.95 if _is_valid_my_number(digits) else 0.5


class MyNumberRecognizer:
    """マイナンバー（個人番号）認識器。

    12 桁の数字列を候補とし、チェックディジットが一致すれば高スコア
    （0.95）、そうでなければ低スコア（0.5）で Entity を返す。番号法の
    法的リスクを踏まえ、recall を優先して pattern-only でも検出する。
    """

    entity_type = MY_NUMBER
    name = "my_number"

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterator[Entity]:
        # 全角ハイフン類は \d{12} のマッチに影響しないため、normalize_digits ではなく
        # 全認識器共通の normalize（digits + hyphens）を使ってよい。
        # Masker 層の事前計算結果（normalized）と互換にすることで再正規化を回避できる。
        return regex_analyze(
            text,
            entity_type=self.entity_type,
            recognizer_name=self.name,
            pattern=_MY_NUMBER_PATTERN,
            validate=_validate,
            normalize_fn=normalize,
            normalized=normalized,
            require_digit_boundary=True,
        )
