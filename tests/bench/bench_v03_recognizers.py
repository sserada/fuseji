"""v0.3 で追加された opt-in 認識器のレイテンシベンチ.

`bench_recognizers.py` が v0.1 デフォルト認識器 5 種を扱うのに対し、
本ファイルは opt-in 系（`default_recognizers()` に含まれない認識器）を
個別に計測する。
"""

from __future__ import annotations

from typing import Any

import pytest

from fuseji.recognizers.corporate_number import CorporateNumberRecognizer
from fuseji.recognizers.jp_address import JpAddressRecognizer


def _sample_text_with_v03(kb: int) -> str:
    """v0.3 認識器のターゲット PII を埋め込んだサンプルテキスト."""
    chunk = (
        "当社 法人番号 7000012050002 は東京都千代田区千代田1-1 にあります。"
        "支店: 神奈川県横浜市西区みなとみらい1-2-3。"
        "本社: 大阪府大阪市北区梅田1-2-3。\n"
    )
    target_bytes = kb * 1024
    chunks_needed = max(1, target_bytes // len(chunk.encode("utf-8")))
    return chunk * chunks_needed


_RECOGNIZERS = [
    ("corporate_number", CorporateNumberRecognizer()),
    ("jp_address", JpAddressRecognizer()),
]


@pytest.mark.parametrize("name,recognizer", _RECOGNIZERS, ids=[r[0] for r in _RECOGNIZERS])
@pytest.mark.parametrize("kb", [1, 4])
def test_v03_recognizer_per_kb(benchmark: Any, name: str, recognizer: Any, kb: int) -> None:
    text = _sample_text_with_v03(kb)
    benchmark.group = f"v03_recognizer_{kb}KB"
    benchmark(lambda: list(recognizer.analyze(text)))


def _pathological_address_text(kb: int) -> str:
    """市区町村サフィックスを含まない pathological 入力 (#141).

    都道府県 anchor + マッチ失敗を誘発する長大漢字列。bounded quantifier 化
    前は 1 マッチ試行ごとに greedy 消費 → 1 文字ずつ縮めて再判定する経路があり、
    O(n²) 級になりうる。
    """
    return "東京都" + "亜" * (kb * 1024)


@pytest.mark.parametrize("kb", [1, 4, 16])
def test_jp_address_pathological(benchmark: Any, kb: int) -> None:
    """worst-case 入力でも線形時間で完了することの回帰防止 (#141)."""
    recognizer = JpAddressRecognizer()
    text = _pathological_address_text(kb)
    benchmark.group = f"jp_address_pathological_{kb}KB"
    benchmark(lambda: list(recognizer.analyze(text)))
