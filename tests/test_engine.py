"""engine.py のテスト（vault 統合・mask_json は別ファイル）."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from fuseji.engine import Masker, _resolve_overlaps
from fuseji.strategies import Redact
from fuseji.types import Entity
from fuseji.vault import InMemoryVault

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


class TestNormalizedDispatch:
    """Masker が事前正規化済みテキストを認識器に渡す挙動 (#24)."""

    def test_normalized_kwarg_を受ける認識器に渡される(self) -> None:
        # normalized を観測する認識器
        observed: dict[str, str | None] = {}

        class ObservingRecognizer:
            entity_type = "X"
            name = "x"

            def analyze(self, text: str, *, normalized: str | None = None) -> Iterable[Entity]:
                observed["normalized"] = normalized
                return iter([])

        m = Masker(recognizers=[ObservingRecognizer()])
        m.detect("０９０ー１２３４")
        # normalize(text) = "090-1234"（数字＋ハイフン正規化）が渡る
        assert observed["normalized"] == "090-1234"

    def test_kwarg_未対応の認識器には_text_のみで呼ばれる(self) -> None:
        called_with: dict[str, object] = {}

        class LegacyRecognizer:
            entity_type = "Y"
            name = "y"

            def analyze(self, text: str) -> Iterable[Entity]:
                called_with["text"] = text
                called_with["has_kwarg"] = False
                return iter([])

        m = Masker(recognizers=[LegacyRecognizer()])
        m.detect("テストテキスト")
        assert called_with["text"] == "テストテキスト"
        # kwarg 未対応認識器のみの場合、normalize 計算自体スキップされる
        assert not m._accepts_normalized[0]

    def test_全認識器が_kwarg_未対応なら_normalize_を計算しない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import fuseji.engine

        class LegacyRecognizer:
            entity_type = "Z"
            name = "z"

            def analyze(self, text: str) -> Iterable[Entity]:
                return iter([])

        calls = {"count": 0}
        original_normalize = fuseji.engine.normalize

        def counting(t: str) -> str:
            calls["count"] += 1
            return original_normalize(t)

        monkeypatch.setattr(fuseji.engine, "normalize", counting)
        m = Masker(recognizers=[LegacyRecognizer()])
        m.detect("テスト")
        assert calls["count"] == 0

    def test_デフォルト認識器でも検出結果が従来と同じ(self) -> None:
        # 既存挙動の互換性確認
        text = "メール a@b.com 電話 ０９０ー１２３４ー５６７８ 郵便〒１２３ー４５６７"
        result = Masker().detect(text)
        types = {e.type for e in result}
        assert types == {"EMAIL", "JP_PHONE_NUMBER", "JP_POSTAL_CODE"}

    def test_VAR_KEYWORD_も_normalized_対応とみなす(self) -> None:
        captured: dict[str, object] = {}

        class KwargsRecognizer:
            entity_type = "W"
            name = "w"

            def analyze(self, text: str, **kwargs: object) -> Iterable[Entity]:
                captured.update(kwargs)
                return iter([])

        m = Masker(recognizers=[KwargsRecognizer()])
        m.detect("０９０")
        assert "normalized" in captured
        assert captured["normalized"] == "090"


class TestVaultStrategyConflict:
    def test_vault_と_strategy_同時指定で_UserWarning(self) -> None:
        """vault が strategy より優先されることを警告で明示."""
        with pytest.warns(UserWarning, match="vault を優先"):
            Masker(strategy=Redact(), vault=InMemoryVault())

    def test_vault_単独なら警告なし(self) -> None:
        import warnings as warn_module

        with warn_module.catch_warnings():
            warn_module.simplefilter("error")  # warning を例外化
            # 警告が出れば test fail
            Masker(vault=InMemoryVault())

    def test_strategy_単独なら警告なし(self) -> None:
        import warnings as warn_module

        with warn_module.catch_warnings():
            warn_module.simplefilter("error")
            Masker(strategy=Redact())

    def test_警告が出ても_vault_の挙動が優先される(self) -> None:
        with pytest.warns(UserWarning):
            m = Masker(strategy=Redact(replacement="REDACTED"), vault=InMemoryVault())
        result = m.mask("a@b.com")
        # Redact ではなく VaultStrategy が動作する → <EMAIL_1> 形式
        assert "<EMAIL_1>" in result.text
        assert "REDACTED" not in result.text
