"""engine.py のテスト（vault 統合・mask_json は別ファイル）."""

from __future__ import annotations

from collections.abc import Iterable

from fuseji.engine import Masker, _resolve_overlaps
from fuseji.strategies import Redact
from fuseji.types import Entity

from .conftest import make_entity as _entity


class _StubRecognizer:
    """テスト用のスタブ認識器."""

    def __init__(self, entity_type: str, entities: list[Entity]) -> None:
        self.entity_type = entity_type
        self._entities = entities

    def analyze(self, text: str) -> Iterable[Entity]:
        return iter(self._entities)


class TestResolveOverlaps:
    def test_重複なし_全て採用(self) -> None:
        es = [_entity("A", "x", 0, 1), _entity("B", "y", 5, 6)]
        assert len(_resolve_overlaps(es)) == 2

    def test_完全重複_スコア高い方を残す(self) -> None:
        es = [_entity("A", "x", 0, 5, score=0.5), _entity("B", "y", 0, 5, score=0.9)]
        result = _resolve_overlaps(es)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_部分重複_長い方を残す(self) -> None:
        # 同スコアの場合は長い span を優先
        es = [
            _entity("A", "x", 0, 5, score=0.8),
            _entity("B", "y", 2, 10, score=0.8),
        ]
        result = _resolve_overlaps(es)
        assert len(result) == 1
        assert result[0].end - result[0].start == 8

    def test_隣接は許容(self) -> None:
        # [0,3) と [3,6) は重複しない
        es = [_entity("A", "x", 0, 3), _entity("B", "y", 3, 6)]
        assert len(_resolve_overlaps(es)) == 2

    def test_位置順で返す(self) -> None:
        es = [
            _entity("A", "x", 10, 15),
            _entity("B", "y", 0, 5),
            _entity("C", "z", 20, 25),
        ]
        result = _resolve_overlaps(es)
        assert [e.start for e in result] == [0, 10, 20]


class TestMaskerDetect:
    def test_デフォルト認識器セットを使用(self) -> None:
        m = Masker()
        entities = m.detect("メール: taro@example.com、電話 090-1234-5678")
        types = {e.type for e in entities}
        assert "EMAIL" in types
        assert "JP_PHONE_NUMBER" in types

    def test_カスタム認識器のみ使用(self) -> None:
        stub = _StubRecognizer("X", [_entity("X", "abc", 0, 3, score=0.9)])
        m = Masker(recognizers=[stub])
        entities = m.detect("abcdef")
        assert len(entities) == 1
        assert entities[0].type == "X"

    def test_threshold_未満は除外(self) -> None:
        stub = _StubRecognizer(
            "X",
            [
                _entity("X", "low", 0, 3, score=0.3),
                _entity("X", "high", 5, 9, score=0.5),
            ],
        )
        m = Masker(recognizers=[stub], threshold=0.4)
        entities = m.detect("low  high")
        assert len(entities) == 1
        assert entities[0].text == "high"

    def test_オーバーラップは解決される(self) -> None:
        stub = _StubRecognizer(
            "X",
            [
                _entity("A", "abc", 0, 3, score=0.5),
                _entity("B", "abcdef", 0, 6, score=0.9),
            ],
        )
        m = Masker(recognizers=[stub])
        entities = m.detect("abcdef")
        assert len(entities) == 1
        assert entities[0].type == "B"


class TestMaskerMask:
    def test_デフォルト戦略は_Placeholder(self) -> None:
        m = Masker()
        result = m.mask("メールは taro@example.com です")
        assert "<EMAIL_1>" in result.text
        assert result.mapping["<EMAIL_1>"] == "taro@example.com"

    def test_Redact_戦略を指定(self) -> None:
        m = Masker(strategy=Redact())
        result = m.mask("メールは taro@example.com です")
        assert "[REDACTED]" in result.text
        assert result.mapping == {}

    def test_検出ゼロなら元テキストそのまま(self) -> None:
        m = Masker()
        result = m.mask("特に何もない普通の文章。")
        assert result.text == "特に何もない普通の文章。"
        assert result.entities == ()

    def test_複数エンティティ(self) -> None:
        m = Masker()
        result = m.mask("メール a@b.com 電話 090-1234-5678 郵便〒123-4567")
        types = {e.type for e in result.entities}
        assert types == {"EMAIL", "JP_PHONE_NUMBER", "JP_POSTAL_CODE"}
