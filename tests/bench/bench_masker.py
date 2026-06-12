"""Masker パイプライン全体のベンチ."""

from __future__ import annotations

from typing import Any

import pytest

from fuseji import Masker


def _build_text(kb: int) -> str:
    """指定 KB 程度の日本語サンプルテキストを作る（PII を一定割合で含む）."""
    chunk = (
        "問い合わせ番号 〒123-4567、"
        "連絡先 090-1234-5678 / taro@example.co.jp、"
        "クレジットカード 4242-4242-4242-4242 です。"
        "本日もよろしくお願いいたします。\n"
    )
    # 1 chunk ≈ 200 bytes（UTF-8 で日本語混在）
    target_bytes = kb * 1024
    chunks_needed = max(1, target_bytes // len(chunk.encode("utf-8")))
    return chunk * chunks_needed


@pytest.fixture(scope="module")
def masker() -> Masker:
    return Masker()


@pytest.mark.parametrize("kb", [1, 4, 16])
def test_masker_full_pipeline(benchmark: Any, masker: Masker, kb: int) -> None:
    """detect → mask の full pipeline レイテンシ."""
    text = _build_text(kb)
    benchmark.group = f"masker_{kb}KB"
    benchmark(masker.mask, text)


@pytest.mark.parametrize("kb", [1, 4, 16])
def test_detect_only(benchmark: Any, masker: Masker, kb: int) -> None:
    text = _build_text(kb)
    benchmark.group = f"detect_{kb}KB"
    benchmark(masker.detect, text)


def _build_many_unique_pii(n: int) -> str:
    """n 個の unique email を 1 つのテキストに並べる worst-case (#181).

    同一 surface の再出現がないため Placeholder の counter / assigned dict が
    線形に増え、Vault assign 経路ではロック取得が n 回連続する。
    cache hit が一切起きないパスの計測。
    """
    return " ".join(f"user{i}@example.com" for i in range(n))


@pytest.mark.parametrize("n", [100, 1000])
def test_masker_many_unique_surfaces(benchmark: Any, masker: Masker, n: int) -> None:
    """同一 surface が再出現しない worst-case Masker.mask (#181)."""
    text = _build_many_unique_pii(n)
    benchmark.group = f"masker_unique_surfaces_n{n}"
    benchmark(masker.mask, text)
