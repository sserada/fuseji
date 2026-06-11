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
def test_masker_full_pipeline(
    benchmark: Any, masker: Masker, kb: int
) -> None:
    """detect → mask の full pipeline レイテンシ."""
    text = _build_text(kb)
    benchmark.group = f"masker_{kb}KB"
    benchmark(masker.mask, text)


@pytest.mark.parametrize("kb", [1, 4, 16])
def test_detect_only(benchmark: Any, masker: Masker, kb: int) -> None:
    text = _build_text(kb)
    benchmark.group = f"detect_{kb}KB"
    benchmark(masker.detect, text)
