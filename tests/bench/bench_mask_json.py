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


def _build_wide_and_deep(n_leaves: int, depth: int) -> dict[str, Any]:
    """worst-case: 幅 n_leaves × 深さ depth の入れ子 dict (#181).

    各レベルで n_leaves 個の flat leaf を持ちつつ、`nested` キーで次の段に続ける。
    再帰 (mask_json の per-level dict 再構築) と per-leaf 処理 (isinstance 判定 +
    Masker.mask 呼び出し) の **相乗効果** を計測する。
    """
    inner: Any = "メール: taro@example.com"
    for _ in range(depth):
        layer = _build_flat(n_leaves)
        layer["nested"] = inner
        inner = layer
    assert isinstance(inner, dict)
    return inner


def test_mask_json_wide_and_deep(benchmark: Any, masker: Masker) -> None:
    """幅 100 × 深さ 10 の worst-case 入れ子 (#181).

    既存の flat (100/1000) / nested (3/10) は独立次元のみカバーしていたが、
    本ケースは「dict キーを伴う再帰」+ 「per-leaf レイテンシ」両方を同時に踏む
    pathological 構造。
    """
    data = _build_wide_and_deep(n_leaves=100, depth=10)
    benchmark.group = "mask_json_worst_case"
    benchmark(masker.mask_json, data)
