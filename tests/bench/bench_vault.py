"""InMemoryVault.restore のスケール曲線ベンチ."""

from __future__ import annotations

from typing import Any

import pytest

from fuseji import InMemoryVault


@pytest.fixture
def vault_with_m_entries(request: pytest.FixtureRequest) -> InMemoryVault:
    """m 個の placeholder が登録済みの Vault を用意."""
    m = request.param
    v = InMemoryVault()
    for i in range(m):
        v.assign("PERSON", f"name_{i}")
    return v


@pytest.mark.parametrize(
    "vault_with_m_entries",
    [10, 100, 1000],
    indirect=True,
    ids=["m=10", "m=100", "m=1000"],
)
def test_vault_restore_scales(
    benchmark: Any, vault_with_m_entries: InMemoryVault
) -> None:
    """1KB の placeholder 散在テキストを m=10/100/1000 で復元."""
    # 1KB 程度の placeholder と素文の混在
    text_parts: list[str] = []
    for i in range(100):
        text_parts.append(f"<PERSON_{i % 10 + 1}> さん、こんにちは。")
    text = "".join(text_parts)

    benchmark.group = "vault_restore"
    benchmark(vault_with_m_entries.restore, text)
