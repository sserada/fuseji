"""日本の郵便番号認識器."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..types import Entity
from .base import has_digit_boundary, normalize

# 〒 + 任意の空白 + 7 桁（ハイフン任意）
_POSTAL_WITH_MARK = re.compile(r"〒\s*\d{3}-?\d{4}")
# XXX-XXXX 形式（ハイフン必須）。区切りなしの 7 桁は誤検出が多いため検出対象から外す。
_POSTAL_WITH_HYPHEN = re.compile(r"\d{3}-\d{4}")

# 文脈語: 周辺にあれば郵便番号らしさが増す
_CONTEXT_WORDS = ("郵便番号", "住所", "postal", "zip", "ZIP")
_CONTEXT_WINDOW = 20


def _has_context(text: str, start: int, end: int) -> bool:
    around = text[max(0, start - _CONTEXT_WINDOW) : end + _CONTEXT_WINDOW]
    return any(w in around for w in _CONTEXT_WORDS)


class JpPostalRecognizer:
    """日本の郵便番号認識器。

    検出パターン:
    - 〒 prefix 付き: score=0.95
    - XXX-XXXX 形式 + 文脈語あり: score=0.9
    - XXX-XXXX 形式単独: score=0.6（recall 優先）

    区切りなしの 7 桁数字は日付・ID 等との誤検出が多いため検出しない。
    """

    entity_type = "JP_POSTAL_CODE"

    def analyze(self, text: str) -> Iterable[Entity]:
        normalized = normalize(text)
        emitted_spans: list[tuple[int, int]] = []

        # 〒付きを先に検出（高 score）
        for m in _POSTAL_WITH_MARK.finditer(normalized):
            start, end = m.start(), m.end()
            emitted_spans.append((start, end))
            yield Entity(
                type=self.entity_type,
                text=text[start:end],
                start=start,
                end=end,
                score=0.95,
                recognizer="jp_postal",
            )

        # XXX-XXXX 形式（〒付き範囲と重複しないもの）
        for m in _POSTAL_WITH_HYPHEN.finditer(normalized):
            start, end = m.start(), m.end()
            if any(s <= start and end <= e for s, e in emitted_spans):
                continue
            # 周辺が数字なら別 ID とみなす
            if has_digit_boundary(normalized, start, end):
                continue
            score = 0.9 if _has_context(normalized, start, end) else 0.6
            yield Entity(
                type=self.entity_type,
                text=text[start:end],
                start=start,
                end=end,
                score=score,
                recognizer="jp_postal",
            )
