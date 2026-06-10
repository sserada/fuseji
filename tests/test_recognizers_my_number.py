"""my_number 認識器のテスト."""

from __future__ import annotations

from fuseji.recognizers.my_number import (
    MyNumberRecognizer,
    _checksum,
    _is_valid_my_number,
)


class TestChecksum:
    def test_既知の有効番号(self) -> None:
        # 123456789018 — 計算で 8 になることを上で検証済み
        assert _checksum("12345678901") == 8

    def test_全ゼロ(self) -> None:
        # 全 0 なら R=0 → checksum=0
        assert _checksum("00000000000") == 0


class TestIsValidMyNumber:
    def test_有効な番号(self) -> None:
        assert _is_valid_my_number("123456789018") is True

    def test_チェックディジット不一致(self) -> None:
        # 末尾を変える
        assert _is_valid_my_number("123456789010") is False

    def test_桁数違い(self) -> None:
        assert _is_valid_my_number("12345678901") is False  # 11 桁
        assert _is_valid_my_number("1234567890123") is False  # 13 桁

    def test_数字以外を含む(self) -> None:
        assert _is_valid_my_number("12345678901a") is False


class TestMyNumberRecognizer:
    def test_有効な番号は高スコア(self) -> None:
        entities = list(MyNumberRecognizer().analyze("番号: 123456789018"))
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "MY_NUMBER"
        assert e.text == "123456789018"
        assert e.score == 0.95
        assert e.recognizer == "my_number"

    def test_チェックディジット失敗でも検出_低スコア(self) -> None:
        # recall 優先で出すが、score は低い
        entities = list(MyNumberRecognizer().analyze("123456789010"))
        assert len(entities) == 1
        assert entities[0].score == 0.5

    def test_全角数字(self) -> None:
        text = "１２３４５６７８９０１８"
        entities = list(MyNumberRecognizer().analyze(text))
        assert len(entities) == 1
        # 元テキストの表層を返す
        assert entities[0].text == text
        assert entities[0].score == 0.95

    def test_13_桁以上の連続数字内では検出しない(self) -> None:
        # "1234567890180" は 13 桁、有効な MN を内包するが別 ID とみなす
        entities = list(MyNumberRecognizer().analyze("1234567890180"))
        assert entities == []

    def test_11_桁は検出しない(self) -> None:
        entities = list(MyNumberRecognizer().analyze("12345678901"))
        assert entities == []

    def test_文中の番号(self) -> None:
        text = "マイナンバーは 123456789018 です"
        entities = list(MyNumberRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert text[e.start : e.end] == "123456789018"

    def test_オフセットが正しい(self) -> None:
        text = "  123456789018  "
        entities = list(MyNumberRecognizer().analyze(text))
        e = entities[0]
        assert text[e.start : e.end] == e.text

    def test_空文字列(self) -> None:
        assert list(MyNumberRecognizer().analyze("")) == []

    def test_文中の複数番号(self) -> None:
        text = "A: 123456789018 B: 234567890121"
        entities = list(MyNumberRecognizer().analyze(text))
        assert len(entities) == 2
