"""マスキング戦略の横並び比較 (#98).

`Placeholder` / `Redact` / `Hash` / `VaultStrategy` を同じ entity 集合に対して
適用し、レイテンシを横並びで比較する。

- Placeholder: dict 採番 + 文字列置換
- Redact: 固定文字列置換のみ（最速の想定）
- Hash: SHA256 計算（surface 種類が多いとコスト増、#96 の LRU 改善対象）
- VaultStrategy: vault.assign × n + 置換（lock オーバーヘッド、#97 の bulk 化対象）
"""

from __future__ import annotations

from typing import Any

import pytest

from fuseji import InMemoryVault, Masker
from fuseji.strategies import Hash, Placeholder, Redact, VaultStrategy
from fuseji.types import Entity


def _build_text_and_entities(n_pii: int) -> tuple[str, list[Entity]]:
    """n 件の email PII を含む合成テキストと対応 Entity リストを生成."""
    parts: list[str] = []
    entities: list[Entity] = []
    pos = 0
    for i in range(n_pii):
        prefix = f"contact{i}: "
        email = f"user{i}@example.com"
        parts.append(prefix)
        pos += len(prefix)
        entities.append(
            Entity(
                type="EMAIL",
                text=email,
                start=pos,
                end=pos + len(email),
                score=1.0,
                recognizer="bench",
            )
        )
        parts.append(email)
        pos += len(email)
        parts.append(" / ")
        pos += 3
    return "".join(parts), entities


@pytest.fixture(scope="module")
def text_and_entities() -> tuple[str, list[Entity]]:
    return _build_text_and_entities(100)


def test_placeholder(benchmark: Any, text_and_entities: tuple[str, list[Entity]]) -> None:
    text, entities = text_and_entities
    benchmark.group = "strategies_100pii"
    benchmark(Placeholder().mask, text, entities)


def test_redact(benchmark: Any, text_and_entities: tuple[str, list[Entity]]) -> None:
    text, entities = text_and_entities
    benchmark.group = "strategies_100pii"
    benchmark(Redact().mask, text, entities)


def test_hash_default(benchmark: Any, text_and_entities: tuple[str, list[Entity]]) -> None:
    """Hash 戦略デフォルト（length=16, keep_mapping=False）."""
    text, entities = text_and_entities
    benchmark.group = "strategies_100pii"
    benchmark(Hash().mask, text, entities)


def test_vault_strategy(benchmark: Any, text_and_entities: tuple[str, list[Entity]]) -> None:
    """VaultStrategy（新規 surface 群を毎回投入）.

    各ラウンドで新しい InMemoryVault を作るため、全 PII が新規 surface 扱いで
    lock 取得を伴う採番が n 回発生する（#97 の bulk 化前後の比較に使える）。
    """
    text, entities = text_and_entities
    benchmark.group = "strategies_100pii"

    def run() -> None:
        VaultStrategy(vault=InMemoryVault()).mask(text, entities)

    benchmark(run)


def test_masker_with_vault(benchmark: Any) -> None:
    """vault 経路を Masker から通したときのレイテンシ（パイプライン全体）."""
    masker = Masker(vault=InMemoryVault())
    text = "メール taro@example.com 連絡先 090-1234-5678 〒123-4567"
    benchmark.group = "masker_with_vault"
    benchmark(masker.mask, text)
