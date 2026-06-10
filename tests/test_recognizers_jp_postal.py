"""jp_postal 認識器のテスト."""

from __future__ import annotations

from fuseji.recognizers.jp_postal import JpPostalRecognizer


class TestJpPostalRecognizer:
    def test_郵便マーク付き(self) -> None:
        entities = list(JpPostalRecognizer().analyze("〒123-4567 東京都..."))
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "JP_POSTAL_CODE"
        assert e.text == "〒123-4567"
        assert e.score == 0.95
        assert e.recognizer == "jp_postal"

    def test_郵便マーク付きハイフンなし(self) -> None:
        entities = list(JpPostalRecognizer().analyze("〒1234567"))
        assert len(entities) == 1
        assert entities[0].text == "〒1234567"
        assert entities[0].score == 0.95

    def test_郵便マークと空白(self) -> None:
        entities = list(JpPostalRecognizer().analyze("〒 123-4567"))
        assert len(entities) == 1
        assert entities[0].text == "〒 123-4567"

    def test_ハイフン形式_文脈語あり(self) -> None:
        entities = list(JpPostalRecognizer().analyze("郵便番号: 123-4567"))
        assert len(entities) == 1
        assert entities[0].text == "123-4567"
        assert entities[0].score == 0.9

    def test_ハイフン形式_文脈語なし(self) -> None:
        entities = list(JpPostalRecognizer().analyze("123-4567"))
        assert len(entities) == 1
        assert entities[0].score == 0.6

    def test_住所文脈で_boost(self) -> None:
        entities = list(JpPostalRecognizer().analyze("住所: 123-4567 東京都"))
        assert entities[0].score == 0.9

    def test_全角数字とハイフン(self) -> None:
        text = "〒１２３ー４５６７"
        entities = list(JpPostalRecognizer().analyze(text))
        assert len(entities) == 1
        # 元テキストの表層を返す
        assert entities[0].text == text

    def test_ハイフンなし_マークなしは検出しない(self) -> None:
        # 7 桁数字単独は誤検出を避けるため検出しない
        assert list(JpPostalRecognizer().analyze("1234567")) == []

    def test_周辺が数字は除外(self) -> None:
        # 10 桁数字内の 7 桁を取らない
        assert list(JpPostalRecognizer().analyze("0123-4567890")) == []

    def test_郵便マーク付きと単体ハイフン形式の重複検出を避ける(self) -> None:
        # 〒 付きで検出した範囲を、後段の XXX-XXXX 検出が重複しない
        text = "〒123-4567"
        entities = list(JpPostalRecognizer().analyze(text))
        assert len(entities) == 1

    def test_複数の郵便番号(self) -> None:
        text = "〒123-4567 と 〒987-6543"
        entities = list(JpPostalRecognizer().analyze(text))
        assert len(entities) == 2

    def test_オフセットが正しい(self) -> None:
        text = "  123-4567  "
        entities = list(JpPostalRecognizer().analyze(text))
        e = entities[0]
        assert text[e.start : e.end] == e.text

    def test_空文字列(self) -> None:
        assert list(JpPostalRecognizer().analyze("")) == []
