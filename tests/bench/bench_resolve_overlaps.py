"""`_resolve_overlaps` のスケール曲線 (#98).

`_resolve_overlaps` は線形スキャンで採用済み span との重なりを判定するため、
入力 entity 数 n に対して O(n²)。NER 有効時など entity 数が数百〜数千に
膨らむ場面での回帰検知と、sweep-line 化 (#95) の before/after 計測に使う。
"""

from __future__ import annotations

from typing import Any

import pytest

from fuseji.engine import _resolve_overlaps
from fuseji.types import Entity


def _build_entities(n: int, *, overlap_ratio: float = 0.0) -> list[Entity]:
    """合成 Entity を `n` 個生成する。

    位置は線形に並べ、`overlap_ratio` の割合で隣接 span を 50% 重ねる。
    重複は `_resolve_overlaps` の競合判定パスを通すために使う。
    """
    span_len = 10
    gap = 5
    entities: list[Entity] = []
    pos = 0
    for i in range(n):
        start = pos
        end = pos + span_len
        # overlap_ratio に応じて次の start を内側に食い込ませる
        if overlap_ratio > 0 and (i % max(1, int(1 / overlap_ratio))) == 0:
            pos = end - int(span_len * 0.5)
        else:
            pos = end + gap
        entities.append(
            Entity(
                type="X",
                text="x" * span_len,
                start=start,
                end=end,
                score=0.5 + 0.0001 * (i % 100),
                recognizer="bench",
            )
        )
    return entities


@pytest.mark.parametrize("n", [10, 100, 1000])
def test_resolve_overlaps_disjoint(benchmark: Any, n: int) -> None:
    """重複なし n entities — 線形スキャンの best case."""
    entities = _build_entities(n)
    benchmark.group = f"resolve_overlaps_disjoint_n{n}"
    benchmark(_resolve_overlaps, entities)


@pytest.mark.parametrize("n", [10, 100, 1000])
def test_resolve_overlaps_dense(benchmark: Any, n: int) -> None:
    """50% 重複を含む密集 n entities — 競合判定パスを多く通す."""
    entities = _build_entities(n, overlap_ratio=0.5)
    benchmark.group = f"resolve_overlaps_dense_n{n}"
    benchmark(_resolve_overlaps, entities)


@pytest.mark.parametrize("n", [100, 1000])
def test_resolve_overlaps_full_overlap(benchmark: Any, n: int) -> None:
    """全 entity が前隣と被る worst-case (#181).

    overlap_ratio=1.0 で毎ステップ span 半分を被せる。`_resolve_overlaps` の
    線形スキャンが採用済み span との競合判定で **最多回数** 走る経路。
    sweep-line 化 (#95) の改善対象。
    """
    entities = _build_entities(n, overlap_ratio=1.0)
    benchmark.group = f"resolve_overlaps_full_overlap_n{n}"
    benchmark(_resolve_overlaps, entities)
