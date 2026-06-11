"""_replace_spans のスケール曲線ベンチ.

#23 で O(n²) を O(n+k) に最適化した効果を確認する。
"""

from __future__ import annotations

from typing import Any

import pytest

from fuseji.strategies import _replace_spans


@pytest.mark.parametrize(
    "k",
    [1, 10, 50, 200],
)
def test_replace_spans_scales(benchmark: Any, k: int) -> None:
    """1KB テキスト、k 個の置換."""
    text = "a" * 1024
    # 等間隔に k 個の span を配置（オーバーラップなし）
    step = max(1, len(text) // (k + 1))
    replacements = [
        (i * step, i * step + 1, "<X>") for i in range(1, k + 1) if i * step + 1 < len(text)
    ]
    benchmark.group = "replace_spans"
    benchmark(_replace_spans, text, replacements)
