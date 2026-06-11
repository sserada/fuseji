"""VaultStrategy の単体テスト（Masker を介さない直接利用）."""

from __future__ import annotations

from fuseji import InMemoryVault, VaultStrategy
from fuseji.types import Entity


def _entity(type_: str, text: str, start: int, end: int) -> Entity:
    return Entity(type=type_, text=text, start=start, end=end, score=1.0, recognizer="test")


class TestVaultStrategy:
    def test_基本動作_vault_の_placeholder_を使う(self) -> None:
        vault = InMemoryVault()
        strategy = VaultStrategy(vault=vault)
        text = "メール a@b.com"
        entities = [_entity("EMAIL", "a@b.com", 4, 11)]
        masked, mapping = strategy.mask(text, entities)
        assert masked == "メール <EMAIL_1>"
        assert mapping == {"<EMAIL_1>": "a@b.com"}

    def test_excluded_type_は番号なし_TYPE_で_mapping_に残らない(self) -> None:
        vault = InMemoryVault()  # MY_NUMBER がデフォルト除外
        strategy = VaultStrategy(vault=vault)
        text = "番号: 123456789018"
        entities = [_entity("MY_NUMBER", "123456789018", 4, 16)]
        masked, mapping = strategy.mask(text, entities)
        assert "<MY_NUMBER>" in masked
        assert "<MY_NUMBER_1>" not in masked  # 番号付きにならない
        assert mapping == {}  # mapping に残らない

    def test_同一_surface_は同一_placeholder_を再利用(self) -> None:
        vault = InMemoryVault()
        strategy = VaultStrategy(vault=vault)
        # 同じテキスト中に同じ surface を 2 回
        text = "a@b.com と a@b.com"
        entities = [
            _entity("EMAIL", "a@b.com", 0, 7),
            _entity("EMAIL", "a@b.com", 10, 17),
        ]
        masked, mapping = strategy.mask(text, entities)
        assert masked == "<EMAIL_1> と <EMAIL_1>"
        assert mapping == {"<EMAIL_1>": "a@b.com"}

    def test_異なる_strategy_呼び出しで_vault_状態が継承される(self) -> None:
        """Vault のセッション一貫性が VaultStrategy 経由でも維持される."""
        vault = InMemoryVault()
        strategy = VaultStrategy(vault=vault)

        # 1 回目
        masked1, _ = strategy.mask("メール a@b.com", [_entity("EMAIL", "a@b.com", 4, 11)])
        # 2 回目（別呼び出し）
        masked2, _ = strategy.mask("再送 a@b.com", [_entity("EMAIL", "a@b.com", 3, 10)])

        # 両方とも同じ placeholder <EMAIL_1>
        assert "<EMAIL_1>" in masked1
        assert "<EMAIL_1>" in masked2

    def test_frozen_かつ_dataclass(self) -> None:
        """設定変更を防ぐため frozen dataclass で実装されている."""
        import dataclasses

        vault = InMemoryVault()
        strategy = VaultStrategy(vault=vault)
        assert dataclasses.is_dataclass(strategy)
        # frozen=True なので属性変更不可
        try:
            strategy.vault = InMemoryVault()  # type: ignore[misc]
        except (dataclasses.FrozenInstanceError, AttributeError):
            pass
        else:
            raise AssertionError("frozen 違反: vault を変更できてしまった")

    def test_空_entities_は素のテキストを返す(self) -> None:
        strategy = VaultStrategy(vault=InMemoryVault())
        masked, mapping = strategy.mask("変更なし", [])
        assert masked == "変更なし"
        assert mapping == {}

    def test_公開_API_経由で_import_できる(self) -> None:
        """fuseji.VaultStrategy として直接 import 可能."""
        import fuseji

        assert fuseji.VaultStrategy is VaultStrategy
        assert "VaultStrategy" in fuseji.__all__
