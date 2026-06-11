"""recognizers/base.py のテスト."""

from __future__ import annotations

import re

import pytest

from fuseji.recognizers.base import (
    default_recognizers,
    normalize,
    normalize_digits,
    normalize_hyphens,
    regex_analyze,
)


class TestNormalizeDigits:
    def test_全角を半角に変換(self) -> None:
        assert normalize_digits("０１２３４５６７８９") == "0123456789"

    def test_半角はそのまま(self) -> None:
        assert normalize_digits("0123456789") == "0123456789"

    def test_混在(self) -> None:
        assert normalize_digits("０9０ー1234") == "090ー1234"

    def test_数字以外は変更なし(self) -> None:
        assert normalize_digits("田中さん") == "田中さん"

    def test_文字数が維持される(self) -> None:
        original = "電話は０９０-１２３４-５６７８まで"
        normalized = normalize_digits(original)
        assert len(normalized) == len(original)


class TestNormalizeHyphens:
    @pytest.mark.parametrize(
        "ch",
        ["‐", "‑", "‒", "–", "—", "―", "−", "ー", "－"],
    )
    def test_各種ハイフン類は半角に(self, ch: str) -> None:
        assert normalize_hyphens(f"090{ch}1234") == "090-1234"

    def test_半角ハイフンはそのまま(self) -> None:
        assert normalize_hyphens("090-1234-5678") == "090-1234-5678"

    def test_ハイフン以外は変更なし(self) -> None:
        assert normalize_hyphens("田中さん") == "田中さん"

    def test_文字数が維持される(self) -> None:
        original = "090ー1234ー5678"
        normalized = normalize_hyphens(original)
        assert len(normalized) == len(original)


class TestNormalize:
    def test_数字とハイフンを同時に正規化(self) -> None:
        assert normalize("０９０ー１２３４ー５６７８") == "090-1234-5678"

    def test_文字数が維持される(self) -> None:
        original = "電話: ０９０ー１２３４ー５６７８"
        assert len(normalize(original)) == len(original)


class TestDefaultRecognizers:
    def test_v0_1_の_5_認識器を返す(self) -> None:
        recs = default_recognizers()
        types = {r.entity_type for r in recs}
        assert types == {
            "EMAIL",
            "CREDIT_CARD",
            "MY_NUMBER",
            "JP_PHONE_NUMBER",
            "JP_POSTAL_CODE",
        }

    def test_戻り値はタプル(self) -> None:
        assert isinstance(default_recognizers(), tuple)

    def test_各認識器は_analyze_を持つ(self) -> None:
        for r in default_recognizers():
            assert callable(r.analyze)

    def test_各認識器は_name_属性を持つ(self) -> None:
        # snake_case 識別子で Entity.recognizer に格納される
        names = {r.name for r in default_recognizers()}
        assert names == {"email", "credit_card", "my_number", "jp_phone", "jp_postal"}


class TestRegexAnalyze:
    def test_validate_なしのときは_default_score(self) -> None:
        pattern = re.compile(r"\d{3}")
        entities = list(
            regex_analyze(
                "abc 123 xyz",
                entity_type="TEST",
                recognizer_name="test",
                pattern=pattern,
                default_score=0.7,
            )
        )
        assert len(entities) == 1
        e = entities[0]
        assert e.type == "TEST"
        assert e.text == "123"
        assert e.start == 4
        assert e.end == 7
        assert e.score == 0.7
        assert e.recognizer == "test"

    def test_validate_が_None_を返すと候補は除外される(self) -> None:
        pattern = re.compile(r"\d+")

        def reject_short(s: str) -> float | None:
            return 0.9 if len(s) >= 3 else None

        entities = list(
            regex_analyze(
                "1 22 333 4444",
                entity_type="N",
                recognizer_name="n",
                pattern=pattern,
                validate=reject_short,
            )
        )
        assert [e.text for e in entities] == ["333", "4444"]
        assert all(e.score == 0.9 for e in entities)

    def test_normalize_fn_適用後にマッチするが元テキストの表層を返す(self) -> None:
        # 全角数字を normalize 後にマッチさせる
        pattern = re.compile(r"\d{3}")
        entities = list(
            regex_analyze(
                "番号: １２３",
                entity_type="N",
                recognizer_name="n",
                pattern=pattern,
                normalize_fn=normalize,
            )
        )
        assert len(entities) == 1
        # 元テキストの表層形（全角）が返る
        assert entities[0].text == "１２３"

    def test_require_digit_boundary_で前後数字を除外(self) -> None:
        pattern = re.compile(r"\d{3}")
        entities = list(
            regex_analyze(
                "abc 1234 xyz",  # 4 桁の中の 3 桁は周辺数字あり
                entity_type="N",
                recognizer_name="n",
                pattern=pattern,
                require_digit_boundary=True,
            )
        )
        assert entities == []

    def test_strip_separators_before_validate_でハイフンを除去(self) -> None:
        pattern = re.compile(r"\d(?:-\d){2}")
        captured: list[str] = []

        def capture(s: str) -> float | None:
            captured.append(s)
            return 0.9

        list(
            regex_analyze(
                "1-2-3",
                entity_type="N",
                recognizer_name="n",
                pattern=pattern,
                validate=capture,
                strip_separators_before_validate=True,
            )
        )
        assert captured == ["123"]
