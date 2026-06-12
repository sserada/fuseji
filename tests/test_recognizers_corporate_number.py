"""corporate_number 認識器のテスト (#126)."""

from __future__ import annotations

import pytest

from fuseji.recognizers.corporate_number import (
    CorporateNumberRecognizer,
    _checksum,
    _is_valid_corporate_number,
)


class TestChecksumAlgorithm:
    """国税庁公開仕様のチェックディジット算出."""

    def test_公開仕様サンプル_7000012050002(self) -> None:
        # 公開仕様の検証例: check=7, body=000012050002
        body = "000012050002"
        assert _checksum(body) == 7

    def test_全桁ゼロの_body_は_checksum_9(self) -> None:
        # Σ Pn × Qn = 0、9 - (0 mod 9) = 9
        # 仕様上 check は 0-9 の範囲だが、ゼロ番号は実在しないので理論値のみ
        body = "000000000000"
        assert _checksum(body) == 9

    @pytest.mark.parametrize(
        "body,expected",
        [
            # 既知の検証パターン（手計算済み）
            ("000012050002", 7),  # 上記
        ],
    )
    def test_既知の有効パターン(self, body: str, expected: int) -> None:
        assert _checksum(body) == expected


class TestIsValid:
    def test_有効な法人番号(self) -> None:
        assert _is_valid_corporate_number("7000012050002") is True

    def test_check_digit_不一致は無効(self) -> None:
        # 同じ body で check digit だけ書き換えると無効
        assert _is_valid_corporate_number("1000012050002") is False

    def test_12_桁は無効(self) -> None:
        assert _is_valid_corporate_number("700001205000") is False

    def test_14_桁は無効(self) -> None:
        assert _is_valid_corporate_number("70000120500023") is False

    def test_数字以外を含むと無効(self) -> None:
        assert _is_valid_corporate_number("700001205000a") is False


class TestCorporateNumberRecognizer:
    def test_有効な法人番号は_高スコア(self) -> None:
        text = "当社の法人番号は 7000012050002 です"
        entities = list(CorporateNumberRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "CORPORATE_NUMBER"
        assert e.text == "7000012050002"
        assert e.score == 0.95
        assert e.recognizer == "corporate_number"

    def test_チェックディジット不一致でも_低スコアで検出_recall_優先(self) -> None:
        # 「13 桁の数字」自体は法人番号の候補なので低スコアで残す（my_number と同方針）
        text = "番号: 1234567890123"
        entities = list(CorporateNumberRecognizer().analyze(text))
        assert len(entities) == 1
        assert entities[0].score == 0.5

    def test_全角数字も検出(self) -> None:
        text = "法人番号 ７０００012050002 提出"
        entities = list(CorporateNumberRecognizer().analyze(text))
        assert len(entities) == 1
        # 元テキストの表層形（全角混在）が返る
        assert entities[0].text == "７０００012050002"
        assert entities[0].score == 0.95

    def test_12_桁数字は検出しない_MY_NUMBER_範囲(self) -> None:
        # MY_NUMBER (12 桁) と区別される
        text = "番号: 123456789012"
        entities = list(CorporateNumberRecognizer().analyze(text))
        assert entities == []

    def test_14_桁以上の数字列内の_13_桁は除外_digit_boundary(self) -> None:
        # 周辺が数字の 13 桁列は別 ID の一部とみなして除外
        text = "ID: 12345678901234567890"
        entities = list(CorporateNumberRecognizer().analyze(text))
        assert entities == []

    def test_オフセットが正しい(self) -> None:
        text = "  7000012050002  "
        entities = list(CorporateNumberRecognizer().analyze(text))
        assert len(entities) == 1
        e = entities[0]
        assert text[e.start : e.end] == e.text

    def test_空文字列(self) -> None:
        assert list(CorporateNumberRecognizer().analyze("")) == []

    def test_複数の法人番号_score_も明示検証(self) -> None:
        # 7000012050002 はチェックディジット適合 → 0.95
        # 5010001030003 は不適合 → recall 優先で 0.5 (#179)
        text = "親会社 7000012050002、子会社 5010001030003"
        entities = sorted(CorporateNumberRecognizer().analyze(text), key=lambda e: e.start)
        assert len(entities) == 2
        assert entities[0].text == "7000012050002"
        assert entities[0].score == 0.95
        assert entities[1].text == "5010001030003"
        assert entities[1].score == 0.5

    def test_デフォルト認識器セットには含まれない(self) -> None:
        # public information のため opt-in 設計
        from fuseji.recognizers.base import default_recognizers

        types = {r.entity_type for r in default_recognizers()}
        assert "CORPORATE_NUMBER" not in types

    def test_明示的に組み込めば_Masker_でも検出される(self) -> None:
        from fuseji import Masker
        from fuseji.recognizers.base import default_recognizers

        m = Masker(recognizers=[*default_recognizers(), CorporateNumberRecognizer()])
        result = m.detect("当社の法人番号は 7000012050002 です")
        types = {e.type for e in result}
        assert "CORPORATE_NUMBER" in types

    def test_normalized_kwarg_を受ける(self) -> None:
        # Masker 層で normalize 1 回化された結果を受けても正しく動作する (#24/#93)
        from fuseji.recognizers.base import normalize

        text = "法人番号 ７０00012050002"
        pre = normalize(text)
        entities = list(CorporateNumberRecognizer().analyze(text, normalized=pre))
        assert len(entities) == 1
        assert entities[0].score == 0.95
