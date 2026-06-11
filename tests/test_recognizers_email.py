"""email 認識器のテスト."""

from __future__ import annotations

from fuseji.recognizers.email import EmailRecognizer


class TestEmailRecognizer:
    def test_標準的なアドレス(self) -> None:
        entities = list(EmailRecognizer().analyze("連絡は taro@example.com まで"))
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "EMAIL"
        assert e.text == "taro@example.com"
        assert e.start == 4
        assert e.end == 20
        assert e.score == 1.0
        assert e.recognizer == "email"

    def test_ドット_プラス_ハイフン_アンダースコアを含む(self) -> None:
        text = "first.last+tag-name_x@sub.example.co.jp"
        entities = list(EmailRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].text == text

    def test_複数のアドレス(self) -> None:
        text = "a@x.com と b@y.jp と c@z.co.uk"
        entities = list(EmailRecognizer().analyze(text))
        assert [e.text for e in entities] == ["a@x.com", "b@y.jp", "c@z.co.uk"]

    def test_日本語の中のアドレス(self) -> None:
        text = "メールアドレスは hello@example.co.jp です"
        entities = list(EmailRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].text == "hello@example.co.jp"

    def test_TLD_が_1_文字なら検出しない(self) -> None:
        # TLD は 2 文字以上
        entities = list(EmailRecognizer().analyze("foo@bar.x"))
        assert entities == []

    def test_アットマークなしは検出しない(self) -> None:
        entities = list(EmailRecognizer().analyze("foo.bar.example.com"))
        assert entities == []

    def test_空文字列(self) -> None:
        assert list(EmailRecognizer().analyze("")) == []

    def test_オフセットが正しい(self) -> None:
        text = "  taro@example.com  "
        entities = list(EmailRecognizer().analyze(text))
        e = entities[0]
        assert text[e.start : e.end] == e.text


class TestEmailUnicodeEdges:
    """Unicode/絵文字/IDN の境界挙動 (#91)."""

    def test_IDN_ドメインは現状検出されない(self) -> None:
        # ローカル部・ドメイン部とも ASCII 限定の RFC-lite パターンなので、
        # 日本語ドメイン (例: 日本語.jp) や Punycode 前の IDN は検出しない。
        # IDN サポートは将来の Issue で別途検討する。
        entities = list(EmailRecognizer().analyze("taro@日本語.jp"))
        assert entities == []

    def test_Punycode_は_ASCII_化されているので検出される(self) -> None:
        # IDN の Punycode 表記は ASCII のため現行 regex でも拾える
        entities = list(EmailRecognizer().analyze("taro@xn--wgv71a.jp"))
        assert len(entities) == 1
        assert entities[0].text == "taro@xn--wgv71a.jp"

    def test_絵文字隣接でもオフセットが正しい(self) -> None:
        # サロゲートペア (U+1F600) の前後でも Python の str はコードポイント
        # 単位で扱うため start/end は安定する
        text = "😀taro@example.com😀"
        entities = list(EmailRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert text[e.start : e.end] == e.text
        assert e.text == "taro@example.com"
