"""ner/base.py のテスト."""

from __future__ import annotations

from collections.abc import Iterable

from fuseji.ner.base import NerBackend
from fuseji.types import Entity


class _DummyBackend:
    """テスト用のダミーバックエンド."""

    def analyze(self, text: str) -> Iterable[Entity]:
        return ()


class TestNerBackendProtocol:
    def test_最小実装が_NerBackend_として扱える(self) -> None:
        backend: NerBackend = _DummyBackend()
        assert list(backend.analyze("テキスト")) == []
