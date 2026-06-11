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
    """テスト用のスタブ認識器。v0.2 Protocol 準拠（normalized kwarg を受け取る）。"""

    def __init__(self, entity_type: str, entities: list[Entity]) -> None:
        self.entity_type = entity_type
        self.name = entity_type.lower()
        self._entities = entities

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterable[Entity]:
        del normalized
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

    def test_disjoint_な大量入力でも正しく全採用(self) -> None:
        # #95 の max_end_so_far 早期採用パスを通すテスト。
        # 100 個の disjoint span を投入し、全て採用されることを確認。
        es = [_entity("X", "s", i * 10, i * 10 + 5, score=0.5 + 0.001 * i) for i in range(100)]
        result = _resolve_overlaps(es)
        assert len(result) == 100

    def test_dense_な重複でも_max_end_の早期採用と協調する(self) -> None:
        # スコア降順で 1 番目に採用される長い span が max_end を底上げするが、
        # その後の重複候補は線形スキャン経路で正しく排除されることを確認。
        es = [
            _entity("A", "long", 0, 100, score=0.9),  # 最初に採用、max_end=100
            _entity("B", "mid", 10, 30, score=0.8),  # 重複 → 拒否
            _entity("C", "mid", 40, 60, score=0.8),  # 重複 → 拒否
            _entity("D", "far", 200, 210, score=0.7),  # disjoint → 早期採用
        ]
        result = _resolve_overlaps(es)
        types = {e.type for e in result}
        assert types == {"A", "D"}


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
    """Masker が事前正規化済みテキストを認識器に渡す挙動 (#24 + #93)."""

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

    def test_normalize_は_detect_ごとに_1_回だけ呼ばれる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import fuseji.engine

        class CountingRecognizer:
            entity_type = "Z"
            name = "z"

            def analyze(self, text: str, *, normalized: str | None = None) -> Iterable[Entity]:
                # normalized を確実に受け取って消費（重複正規化が起きないことを確認）
                _ = normalized
                return iter([])

        calls = {"count": 0}
        original_normalize = fuseji.engine.normalize

        def counting(t: str) -> str:
            calls["count"] += 1
            return original_normalize(t)

        monkeypatch.setattr(fuseji.engine, "normalize", counting)
        # 認識器を 3 つ登録しても normalize は 1 回だけ呼ばれる
        m = Masker(recognizers=[CountingRecognizer(), CountingRecognizer(), CountingRecognizer()])
        m.detect("テスト")
        assert calls["count"] == 1

    def test_デフォルト認識器でも検出結果が従来と同じ(self) -> None:
        # 既存挙動の互換性確認
        text = "メール a@b.com 電話 ０９０ー１２３４ー５６７８ 郵便〒１２３ー４５６７"
        result = Masker().detect(text)
        types = {e.type for e in result}
        assert types == {"EMAIL", "JP_PHONE_NUMBER", "JP_POSTAL_CODE"}

    def test_VAR_KEYWORD_を受ける認識器にも_normalized_が渡る(self) -> None:
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

    def test_normalized_kwarg_を受けない認識器は_TypeError(self) -> None:
        # v0.2 以降、Recognizer.analyze は normalized kwarg を受け取る必要がある。
        # 後方互換のための inspect ベース dispatch は廃止された。
        class NonCompliantRecognizer:
            entity_type = "Q"
            name = "q"

            def analyze(self, text: str) -> Iterable[Entity]:
                return iter([])

        m = Masker(recognizers=[NonCompliantRecognizer()])
        with pytest.raises(TypeError):
            m.detect("テスト")


class TestCrossRecognizerOverlap:
    """デフォルト認識器セットでのクロス認識器干渉・境界判定の回帰テスト (#89).

    `_resolve_overlaps` + `require_digit_boundary` の組合せで意図された挙動が、
    リファクタや認識器変更で黙って壊れていないことを保証する。
    """

    def test_16桁_CC_は_内部の_12桁_MN_候補を吸収する(self) -> None:
        # `4242424242424242` は Luhn 通過の 16 桁 CC。内部の任意 12 桁部分は
        # MyNumberRecognizer の \d{12} パターンにマッチし得るが、
        # require_digit_boundary=True で前後数字を見て除外される（→ MN は発火しない）。
        result = Masker().detect("カード番号 4242424242424242 です")
        types = {e.type for e in result}
        assert types == {"CREDIT_CARD"}
        assert len(result) == 1

    def test_CC_と_MN_が_スペース区切りで隣接した場合は_独立に検出される(self) -> None:
        # `4242424242424242` (Luhn 通過 CC) と `123456789018` (12 桁 MN)
        # の間にスペースが入れば、digit boundary が崩れないので両方発火する。
        result = Masker().detect("カード 4242424242424242 番号 123456789018")
        types = {e.type for e in result}
        assert types == {"CREDIT_CARD", "MY_NUMBER"}

    def test_フリーダイヤルと_MN_が隣接しても_独立検出される(self) -> None:
        # 0120-555-7890（11 桁フリーダイヤル）と 234567890123（12 桁 MN）が
        # 短いテキストに同居しても、それぞれ独立に検出される。
        result = Masker().detect("連絡先 0120-555-7890 番号 234567890123")
        types = {e.type for e in result}
        assert types == {"JP_PHONE_NUMBER", "MY_NUMBER"}

    def test_全角ハイフン混在で複数認識器が独立発火する(self) -> None:
        # 携帯電話番号（全角数字＋全角ハイフン）と 12 桁 MN（全角数字）の組合せ
        text = "TEL: ０９０ー１２３４ー５６７８ ID: ５６７８９０１２３４５６"
        result = Masker().detect(text)
        types = {e.type for e in result}
        assert types == {"JP_PHONE_NUMBER", "MY_NUMBER"}

    def test_CC_と_MN_が_セパレーターなしで連結したら_どちらも発火しない(self) -> None:
        # 16 桁 CC 直後に 12 桁 MN を連結した 28 桁数字列は、CC パターンの
        # 上限（19 桁）を超え、MN の digit boundary 判定で前後数字あり扱いとなり
        # 双方除外される（fail-closed 寄りの安全側挙動）。
        result = Masker().detect("4242424242424242123456789018")
        assert result == ()

    def test_メールアドレス内の数字列は_他認識器に拾われない(self) -> None:
        # `user1234567890@example.com` のローカル部に 10 桁数字が含まれるが、
        # EMAIL の方が長い span で勝つ（オーバーラップ解決）。
        result = Masker().detect("メール user1234567890@example.com まで")
        types = {e.type for e in result}
        assert "EMAIL" in types
        assert "JP_PHONE_NUMBER" not in types

    def test_郵便番号と電話番号が混在しても両方検出される(self) -> None:
        # 〒形式の郵便番号と固定電話 10 桁が混在
        result = Masker().detect("〒123-4567 東京都… 03-1234-5678")
        types = {e.type for e in result}
        assert "JP_POSTAL_CODE" in types
        assert "JP_PHONE_NUMBER" in types


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
        vault = InMemoryVault(nonce="t")
        with pytest.warns(UserWarning):
            m = Masker(strategy=Redact(replacement="REDACTED"), vault=vault)
        result = m.mask("a@b.com")
        # Redact ではなく VaultStrategy が動作する → <EMAIL_1_t> 形式（#81 nonce 付き）
        assert "<EMAIL_1_t>" in result.text
        assert "REDACTED" not in result.text
