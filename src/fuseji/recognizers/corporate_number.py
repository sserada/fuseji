"""法人番号（Corporate Number）認識器 (#126).

国税庁が公開する 13 桁の法人識別番号。マイナンバーと違い公開情報だが、
B2B 契約やベンダー管理のログ等で第三者向けマスクが必要なケースがある。

仕様（https://www.houjin-bangou.nta.go.jp/setsumei/index.html）:
- 13 桁の数字
- 1 桁目（最上位）= チェックディジット
- 2-13 桁目（12 桁）= 基礎番号
- チェックディジット = 9 - ((Σ Pn × Qn) mod 9)
  - n: 基礎番号の右からの桁位置（1..12）
  - Pn: 基礎番号の n 桁目の数字
  - Qn: n が奇数なら 1、偶数なら 2

`default_recognizers()` には含めない（公開情報のため強い検出ニーズは
利用者次第。明示的に `recognizers=[...] + [CorporateNumberRecognizer()]`
で組み込む）。
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..entity_types import CORPORATE_NUMBER
from ..types import Entity
from .base import normalize, regex_analyze

# 13 桁の数字。セパレーターは標準的に使用されないため `\d{13}` で十分。
_CORPORATE_NUMBER_PATTERN = re.compile(r"\d{13}")


def _checksum(body_12_digits: str) -> int:
    """基礎番号 12 桁から 1 桁目のチェックディジットを算出（国税庁公開仕様）.

    右から n=1 まで巡回し、Pn = body[12 - n]、Qn = 1 (n が奇数) or 2 (偶数)。
    s = Σ Pn × Qn、check = 9 - (s mod 9)。
    """
    s = 0
    for n in range(1, 13):
        p = int(body_12_digits[12 - n])  # 右から n 番目
        q = 1 if n % 2 == 1 else 2
        s += p * q
    return 9 - (s % 9)


def _is_valid_corporate_number(digits: str) -> bool:
    """13 桁数字列が有効な法人番号か検査."""
    if len(digits) != 13 or not digits.isdigit():
        return False
    check_digit = int(digits[0])
    body = digits[1:]
    return _checksum(body) == check_digit


def _validate(digits: str) -> float | None:
    """チェックディジット一致なら 0.95、不一致でも 0.5 で採用（recall 優先、my_number 同等）."""
    return 0.95 if _is_valid_corporate_number(digits) else 0.5


class CorporateNumberRecognizer:
    """法人番号認識器（公開情報のため opt-in、#126）。

    13 桁の数字列を候補とし、チェックディジットが一致すれば高スコア
    （0.95）、そうでなければ低スコア（0.5）で Entity を返す。検出は
    `default_recognizers()` には含まれず、明示的に組み込む:

    Example:
        >>> from fuseji import Masker
        >>> from fuseji.recognizers.base import default_recognizers
        >>> from fuseji.recognizers.corporate_number import CorporateNumberRecognizer
        >>> masker = Masker(
        ...     recognizers=[*default_recognizers(), CorporateNumberRecognizer()]
        ... )
        >>> result = masker.detect("当社の法人番号は 7000012050002 です")
        >>> sorted({e.type for e in result})
        ['CORPORATE_NUMBER']
    """

    entity_type = CORPORATE_NUMBER
    name = "corporate_number"

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterator[Entity]:
        # 全角ハイフン類は \d{13} のマッチに影響しないため、全認識器共通の
        # `normalize`（digits + hyphens）を normalize_fn に採用（my_number と
        # 同じ方針）。Masker 層が事前計算した normalized も再利用可能。
        return regex_analyze(
            text,
            entity_type=self.entity_type,
            recognizer_name=self.name,
            pattern=_CORPORATE_NUMBER_PATTERN,
            validate=_validate,
            normalize_fn=normalize,
            normalized=normalized,
            require_digit_boundary=True,
        )
