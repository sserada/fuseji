"""`Masker.mask_json` のスケール曲線 (#98).

dict/list 再帰の `_mask_value` は per-leaf で isinstance チェックを行い、
dict 値の更新では新しい dict を毎回構築するため、leaf 数とネスト深度の
両方でアロケーションが効く。本ベンチで:

- 100 / 1000 leaf の flat 構造
- ネスト 3 / 10 段の構造

を計測し、mask_json 経路の回帰検知に使う。
"""

from __future__ import annotations

from typing import Any

import pytest

from fuseji import Masker


def _build_flat(n_leaves: int) -> dict[str, str]:
    """n 個の文字列 leaf を持つ flat dict を生成。一部に PII を埋める。"""
    return {
        f"key_{i}": (f"value_{i} taro{i}@example.com" if i % 5 == 0 else f"value_{i}")
        for i in range(n_leaves)
    }


def _build_nested(depth: int) -> dict[str, Any]:
    """指定深度の入れ子 dict を生成。leaf に PII を 1 件含む。"""
    leaf: Any = "メール: taro@example.com"
    for _ in range(depth):
        leaf = {"nested": leaf}
    assert isinstance(leaf, dict)
    return leaf


@pytest.fixture(scope="module")
def masker() -> Masker:
    return Masker()


@pytest.mark.parametrize("n_leaves", [100, 1000])
def test_mask_json_flat(benchmark: Any, masker: Masker, n_leaves: int) -> None:
    """flat dict（leaf 数で振る）のスループット計測."""
    data = _build_flat(n_leaves)
    benchmark.group = f"mask_json_flat_n{n_leaves}"
    benchmark(masker.mask_json, data)


@pytest.mark.parametrize("depth", [3, 10])
def test_mask_json_nested(benchmark: Any, masker: Masker, depth: int) -> None:
    """入れ子 dict（ネスト深度で振る）のレイテンシ計測."""
    data = _build_nested(depth)
    benchmark.group = f"mask_json_nested_d{depth}"
    benchmark(masker.mask_json, data)
