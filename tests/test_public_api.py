"""公開 API（fuseji.__init__）のテスト."""

from __future__ import annotations

import fuseji


class TestPublicApi:
    def test_主要シンボルが_re_export_されている(self) -> None:
        # すべて fuseji.X でアクセスできる
        assert fuseji.Masker is not None
        assert fuseji.Entity is not None
        assert fuseji.MaskResult is not None
        assert fuseji.Placeholder is not None
        assert fuseji.Redact is not None
        assert fuseji.Hash is not None
        assert fuseji.MaskStrategy is not None
        assert fuseji.Vault is not None
        assert fuseji.InMemoryVault is not None

    def test___all___に主要シンボルが含まれる(self) -> None:
        expected = {
            "Entity",
            "FusejiError",
            "Hash",
            "InMemoryVault",
            "InvalidConfigError",
            "InvalidEntityError",
            "MaskResult",
            "MaskStrategy",
            "Masker",
            "Placeholder",
            "Redact",
            "Vault",
            "__version__",
        }
        assert set(fuseji.__all__) == expected

    def test_例外階層が_FusejiError_でも_ValueError_でも拾える(self) -> None:
        # InvalidEntityError は FusejiError かつ ValueError の多重継承
        try:
            fuseji.Entity(type="X", text="a", start=-1, end=0, score=0.5, recognizer="r")
        except fuseji.FusejiError as e:
            assert isinstance(e, fuseji.InvalidEntityError)
            assert isinstance(e, ValueError)
        else:
            raise AssertionError("例外が発生しなかった")

        # 既存コードの except ValueError もそのまま動く（互換性）
        try:
            fuseji.Hash(length=0)
        except ValueError as e:
            assert isinstance(e, fuseji.InvalidConfigError)
            assert isinstance(e, fuseji.FusejiError)
        else:
            raise AssertionError("例外が発生しなかった")

    def test_quickstart_動作(self) -> None:
        # README に載せる想定のクイックスタート
        masker = fuseji.Masker()
        result = masker.mask("メール: taro@example.com")
        assert isinstance(result, fuseji.MaskResult)
        assert "<EMAIL_1>" in result.text
        assert result.mapping["<EMAIL_1>"] == "taro@example.com"

    def test_version_属性(self) -> None:
        assert isinstance(fuseji.__version__, str)
