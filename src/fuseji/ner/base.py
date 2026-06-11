"""NER バックエンドのプロトコル定義."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from ..types import Entity


class NerBackend(Protocol):
    """NER バックエンドのプロトコル。

    認識器（regex/checksum）が拾えない、文中の自然な名詞句（人名・地名・組織名等）を
    機械学習モデルで検出するためのインタフェース。Recognizer プロトコルと互換だが、
    モデル依存のため optional extra として分離する。
    """

    def analyze(self, text: str) -> Iterator[Entity]: ...
