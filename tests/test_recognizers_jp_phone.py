"""jp_phone 認識器のテスト."""

from __future__ import annotations

import pytest

from fuseji.recognizers.jp_phone import JpPhoneRecognizer


class TestJpPhoneRecognizer:
    @pytest.mark.parametrize(
        "text,expected_text",
        [
            ("090-1234-5678", "090-1234-5678"),
            ("080-1234-5678", "080-1234-5678"),
            ("070-1234-5678", "070-1234-5678"),
        ],
    )
    def test_携帯番号(self, text: str, expected_text: str) -> None:
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "JP_PHONE_NUMBER"
        assert e.text == expected_text
        assert e.score == 0.95
        assert e.recognizer == "jp_phone"

    @pytest.mark.parametrize(
        "text",
        [
            "0120-123-456",  # 10 桁
            "0120-123-4567",  # 11 桁
            "0120-12-3456",  # 11 桁別形式
        ],
    )
    def test_フリーダイヤル(self, text: str) -> None:
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.95

    def test_ナビダイヤル(self) -> None:
        entities = list(JpPhoneRecognizer().analyze("0570-123-456"))
        assert len(entities) == 1
        assert entities[0].score == 0.95

    @pytest.mark.parametrize(
        "text",
        [
            "03-1234-5678",  # 東京
            "06-1234-5678",  # 大阪
            "011-123-4567",  # 札幌
            "045-123-4567",  # 横浜
        ],
    )
    def test_固定電話(self, text: str) -> None:
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.85  # 固定は携帯より少し低い信頼度

    def test_空白区切り(self) -> None:
        entities = list(JpPhoneRecognizer().analyze("090 1234 5678"))
        assert len(entities) == 1
        assert entities[0].text == "090 1234 5678"

    def test_セパレーターなし(self) -> None:
        entities = list(JpPhoneRecognizer().analyze("09012345678"))
        assert len(entities) == 1
        assert entities[0].text == "09012345678"

    def test_全角数字(self) -> None:
        text = "０９０-１２３４-５６７８"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        # 元テキストの表層を返す
        assert entities[0].text == text

    def test_全角ハイフン(self) -> None:
        text = "090ー1234ー5678"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].text == text

    def test_全角混在(self) -> None:
        text = "０９０ー１２３４ー５６７８"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].text == text

    def test_先頭が_0_でないものは検出しない(self) -> None:
        assert list(JpPhoneRecognizer().analyze("123-456-7890")) == []

    def test_短すぎる桁は検出しない(self) -> None:
        assert list(JpPhoneRecognizer().analyze("03-1234")) == []  # 6 桁
        assert list(JpPhoneRecognizer().analyze("0312345")) == []  # 7 桁

    def test_12_桁以上の連続数字は検出しない(self) -> None:
        # マイナンバー（12桁）と区別する
        assert list(JpPhoneRecognizer().analyze("123456789012")) == []

    def test_文中の電話番号(self) -> None:
        text = "電話: 090-1234-5678 まで"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].text == "090-1234-5678"

    def test_複数の電話番号(self) -> None:
        text = "携帯 090-1234-5678 自宅 03-1234-5678"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 2

    def test_オフセットが正しい(self) -> None:
        text = "  090-1234-5678  "
        entities = list(JpPhoneRecognizer().analyze(text))
        e = entities[0]
        assert text[e.start : e.end] == e.text

    def test_空文字列(self) -> None:
        assert list(JpPhoneRecognizer().analyze("")) == []


class TestJpPhoneUnicodeEdges:
    """Unicode セパレーターやオフセット境界の回帰テスト (#91)."""

    def test_全角空白を許容する(self) -> None:
        # U+3000 IDEOGRAPHIC SPACE は \s にマッチするので電話番号として扱える
        text = "TEL: 090　1234　5678"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.95

    def test_ノーブレークスペースを許容する(self) -> None:
        # U+00A0 NO-BREAK SPACE も \s にマッチ
        text = "TEL: 090 1234 5678"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.95

    def test_絵文字隣接でもオフセットが正しい(self) -> None:
        # サロゲートペアを含む絵文字 (U+1F600) の前後でも Python の str は
        # コードポイント単位で扱うため start/end は安定
        text = "😀090-1234-5678😀"
        entities = list(JpPhoneRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert text[e.start : e.end] == e.text
