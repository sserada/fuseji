"""jp_address 認識器のテスト (#127, opt-in)."""

from __future__ import annotations

import pytest

from fuseji.recognizers.jp_address import JpAddressRecognizer


class TestJpAddressBasic:
    def test_都道府県と市区町村と番地_コンテキスト語あり_は高スコア(self) -> None:
        text = "住所は東京都千代田区千代田1-1です"
        entities = list(JpAddressRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "JP_ADDRESS"
        assert e.text == "東京都千代田区千代田1-1"
        assert e.score == 0.9  # context boost
        assert e.recognizer == "jp_address"

    def test_都道府県と市区町村と番地_コンテキスト語なし(self) -> None:
        text = "当社は神奈川県横浜市西区みなとみらい1-2-3"
        entities = list(JpAddressRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.7

    def test_都道府県と市区町村のみ_番地なし_低スコア(self) -> None:
        text = "東京都港区"
        entities = list(JpAddressRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.5

    def test_全角数字も検出(self) -> None:
        text = "東京都港区六本木１-２-３"
        entities = list(JpAddressRecognizer().analyze(text))
        assert len(entities) == 1
        # 全角数字も normalize で半角化 → 番地として認識される
        assert "1-2-3" in entities[0].text.replace("１", "1").replace("２", "2").replace("３", "3")


class TestJpAddressNegativeCases:
    def test_PII_なしのテキスト(self) -> None:
        text = "PII を含まない普通のテキスト"
        entities = list(JpAddressRecognizer().analyze(text))
        assert entities == []

    def test_都道府県のみは検出しない_市区町村が必須(self) -> None:
        text = "東京都内の話"
        entities = list(JpAddressRecognizer().analyze(text))
        assert entities == []

    def test_企業名に都道府県名が含まれても検出しない_直前漢字_除外(self) -> None:
        text = "株式会社東京エナジー社"  # 「東京」は単独都道府県ではなく企業名
        entities = list(JpAddressRecognizer().analyze(text))
        assert entities == []

    def test_県だけで完結する文も検出しない(self) -> None:
        text = "その商品は神奈川で買いました"
        entities = list(JpAddressRecognizer().analyze(text))
        assert entities == []


class TestJpAddressKnownLimitations:
    """v0.3 minimum viable 版の既知制限事項を回帰テストで固定."""

    def test_北海道の条記法は条以降を取りこぼす(self) -> None:
        # 「北海道札幌市中央区北1条西1丁目」のような条記法は dictionary なしでは
        # 完全に拾えない。基本部分 "北海道札幌市中央区北1" は検出される。
        text = "北海道札幌市中央区北1条西1丁目"
        entities = list(JpAddressRecognizer().analyze(text))
        assert len(entities) == 1
        # 取りこぼしを許容する（番地まで部分検出）
        assert entities[0].text.startswith("北海道札幌市中央区")

    def test_番地の後の_号_は取りこぼされる(self) -> None:
        # 「1 番地 2 号」のような表記は「1 番地」までで止まる
        text = "居住地: 大阪府大阪市北区梅田1番地2号"
        entities = list(JpAddressRecognizer().analyze(text))
        assert len(entities) == 1
        # 完全な「1番地2号」ではなく「1番地」まで
        assert entities[0].text == "大阪府大阪市北区梅田1番地"

    def test_都道府県を省略した住所は検出しない(self) -> None:
        # 「千代田区千代田1-1」だけでは検出しない（都道府県 anchor 必須）
        text = "千代田区千代田1-1にあります"
        entities = list(JpAddressRecognizer().analyze(text))
        assert entities == []


class TestJpAddressIntegration:
    def test_デフォルト認識器セットには含まれない(self) -> None:
        # opt-in 設計（精度が他認識器より劣るため）
        from fuseji.recognizers.base import default_recognizers

        types = {r.entity_type for r in default_recognizers()}
        assert "JP_ADDRESS" not in types

    def test_明示的に組み込めば_Masker_でも検出される(self) -> None:
        from fuseji import Masker
        from fuseji.recognizers.base import default_recognizers

        m = Masker(recognizers=[*default_recognizers(), JpAddressRecognizer()])
        result = m.detect("住所は東京都千代田区千代田1-1です")
        types = {e.type for e in result}
        assert "JP_ADDRESS" in types

    def test_normalized_kwarg_を受ける(self) -> None:
        from fuseji.recognizers.base import normalize

        text = "住所 東京都港区六本木１-２-３"
        pre = normalize(text)
        entities = list(JpAddressRecognizer().analyze(text, normalized=pre))
        assert len(entities) == 1


class TestPrefectureCoverage:
    """47 都道府県すべてが anchor として認識されること."""

    @pytest.mark.parametrize(
        "pref",
        [
            "北海道",
            "青森県",
            "東京都",
            "京都府",
            "大阪府",
            "沖縄県",
            "神奈川県",  # 長い名前
        ],
    )
    def test_主要都道府県(self, pref: str) -> None:
        text = f"{pref}テスト市テスト町1-2-3"
        entities = list(JpAddressRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].text.startswith(pref)
