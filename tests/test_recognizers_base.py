"""recognizers/base.py のテスト."""

from __future__ import annotations

import pytest

from fuseji.recognizers.base import (
    default_recognizers,
    normalize,
    normalize_digits,
    normalize_hyphens,
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
