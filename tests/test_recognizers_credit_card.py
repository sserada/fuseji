"""credit_card 認識器のテスト."""

from __future__ import annotations

import pytest

from fuseji.recognizers.credit_card import CreditCardRecognizer, _luhn


class TestLuhn:
    @pytest.mark.parametrize(
        "number",
        [
            "4242424242424242",  # Stripe テスト VISA
            "4111111111111111",  # 一般的なテスト VISA
            "5555555555554444",  # MasterCard テスト
            "378282246310005",  # Amex テスト 15 桁
            "6011111111111117",  # Discover テスト
            "3530111333300000",  # JCB テスト
        ],
    )
    def test_有効なカード番号は通過(self, number: str) -> None:
        assert _luhn(number) is True

    @pytest.mark.parametrize(
        "number",
        ["4242424242424241", "1234567890123456", "0000000000000001"],
    )
    def test_無効なカード番号は通過しない(self, number: str) -> None:
        assert _luhn(number) is False


class TestCreditCardRecognizer:
    def test_セパレーターなしの_VISA(self) -> None:
        entities = list(CreditCardRecognizer().analyze("カード番号: 4242424242424242"))
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "CREDIT_CARD"
        assert e.text == "4242424242424242"
        assert e.score == 0.95
        assert e.recognizer == "credit_card"

    def test_ハイフン区切り(self) -> None:
        entities = list(CreditCardRecognizer().analyze("4242-4242-4242-4242"))
        assert len(entities) == 1
        assert entities[0].text == "4242-4242-4242-4242"

    def test_空白区切り(self) -> None:
        entities = list(CreditCardRecognizer().analyze("4242 4242 4242 4242"))
        assert len(entities) == 1
        assert entities[0].text == "4242 4242 4242 4242"

    def test_全角ハイフン区切り(self) -> None:
        text = "4242ー4242ー4242ー4242"
        entities = list(CreditCardRecognizer().analyze(text))
        assert len(entities) == 1
        # 元テキストの表層を返す
        assert entities[0].text == text

    def test_全角数字(self) -> None:
        text = "４２４２４２４２４２４２４２４２"
        entities = list(CreditCardRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].text == text

    def test_全角数字と全角ハイフンの混在(self) -> None:
        text = "４２４２ー４２４２ー４２４２ー４２４２"
        entities = list(CreditCardRecognizer().analyze(text))
        assert len(entities) == 1

    def test_Amex_15_桁(self) -> None:
        entities = list(CreditCardRecognizer().analyze("3782 822463 10005"))
        assert len(entities) == 1

    def test_Luhn_失敗は検出しない(self) -> None:
        # 16 桁あるが Luhn 無効
        entities = list(CreditCardRecognizer().analyze("1234567890123456"))
        assert entities == []

    def test_短すぎる桁は検出しない(self) -> None:
        # 12 桁
        entities = list(CreditCardRecognizer().analyze("123456789012"))
        assert entities == []

    def test_電話番号は検出しない(self) -> None:
        # 11 桁、Luhn 通過しても regex の桁数下限で除外
        entities = list(CreditCardRecognizer().analyze("090-1234-5678"))
        assert entities == []

    def test_オフセットが正しい(self) -> None:
        text = "  4242-4242-4242-4242  "
        entities = list(CreditCardRecognizer().analyze(text))
        e = entities[0]
        assert text[e.start : e.end] == e.text

    def test_空文字列(self) -> None:
        assert list(CreditCardRecognizer().analyze("")) == []


class TestCreditCardUnicodeEdges:
    """Unicode/絵文字境界の回帰テスト (#91)."""

    def test_全角空白セパレーターを許容する(self) -> None:
        # U+3000 IDEOGRAPHIC SPACE は \s にマッチするのでカード番号として扱える
        text = "番号 4242　4242　4242　4242"
        entities = list(CreditCardRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.95

    def test_絵文字隣接でもオフセットが正しい(self) -> None:
        # サロゲートペア (U+1F4B3) の前後でも Python の str はコードポイント
        # 単位で扱うため start/end は安定
        text = "💳4242-4242-4242-4242💳"
        entities = list(CreditCardRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert text[e.start : e.end] == e.text
