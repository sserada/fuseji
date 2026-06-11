"""個別認識器のレイテンシベンチ."""

from __future__ import annotations

from typing import Any

import pytest

from fuseji.recognizers.credit_card import CreditCardRecognizer
from fuseji.recognizers.email import EmailRecognizer
from fuseji.recognizers.jp_phone import JpPhoneRecognizer
from fuseji.recognizers.jp_postal import JpPostalRecognizer
from fuseji.recognizers.my_number import MyNumberRecognizer


def _sample_text(kb: int) -> str:
    chunk = (
        "問い合わせ番号 〒123-4567、"
        "連絡先 090-1234-5678 / taro@example.co.jp、"
        "クレジットカード 4242-4242-4242-4242 です。"
        "マイナンバー 123456789018。\n"
    )
    target_bytes = kb * 1024
    chunks_needed = max(1, target_bytes // len(chunk.encode("utf-8")))
    return chunk * chunks_needed


_RECOGNIZERS = [
    ("email", EmailRecognizer()),
    ("credit_card", CreditCardRecognizer()),
    ("my_number", MyNumberRecognizer()),
    ("jp_phone", JpPhoneRecognizer()),
    ("jp_postal", JpPostalRecognizer()),
]


@pytest.mark.parametrize("name,recognizer", _RECOGNIZERS, ids=[r[0] for r in _RECOGNIZERS])
@pytest.mark.parametrize("kb", [1, 4])
def test_recognizer_per_kb(benchmark: Any, name: str, recognizer: Any, kb: int) -> None:
    text = _sample_text(kb)
    benchmark.group = f"recognizer_{kb}KB"
    benchmark(lambda: list(recognizer.analyze(text)))
