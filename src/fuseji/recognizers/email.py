"""メールアドレス認識器（RFC-lite）."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..entity_types import EMAIL
from ..types import Entity

# RFC 5322 完全準拠ではないが、実用上 99% のアドレスを拾える簡易パターン。
# ローカル部: 英数 と . _ % + - を許容
# ドメイン部: 英数とハイフン、ドット区切り、TLD は 2 文字以上の英字
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


class EmailRecognizer:
    """メールアドレス認識器。"""

    entity_type = EMAIL

    def analyze(self, text: str) -> Iterable[Entity]:
        for m in _EMAIL_PATTERN.finditer(text):
            yield Entity(
                type=self.entity_type,
                text=m.group(),
                start=m.start(),
                end=m.end(),
                score=1.0,
                recognizer="email",
            )
