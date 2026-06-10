"""vault.py のテスト."""

from __future__ import annotations

from fuseji.vault import InMemoryVault


class TestAssign:
    def test_新規_surface_に_placeholder_を割当(self) -> None:
        v = InMemoryVault()
        assert v.assign("PERSON", "田中") == "<PERSON_1>"

    def test_同一_type_surface_は同一_placeholder(self) -> None:
        v = InMemoryVault()
        first = v.assign("PERSON", "田中")
        second = v.assign("PERSON", "田中")
        assert first == second == "<PERSON_1>"

    def test_異なる_surface_は別番号(self) -> None:
        v = InMemoryVault()
        assert v.assign("PERSON", "田中") == "<PERSON_1>"
        assert v.assign("PERSON", "佐藤") == "<PERSON_2>"

    def test_type_ごとに番号系列が独立(self) -> None:
        v = InMemoryVault()
        assert v.assign("PERSON", "田中") == "<PERSON_1>"
        assert v.assign("EMAIL", "x@y.z") == "<EMAIL_1>"
        assert v.assign("PERSON", "佐藤") == "<PERSON_2>"
        assert v.assign("EMAIL", "a@b.c") == "<EMAIL_2>"

    def test_同じ_surface_でも_type_が違えば別_placeholder(self) -> None:
        v = InMemoryVault()
        p1 = v.assign("PERSON", "山田")
        p2 = v.assign("COMPANY", "山田")
        assert p1 == "<PERSON_1>"
        assert p2 == "<COMPANY_1>"
        assert p1 != p2


class TestExcludedTypes:
    def test_デフォルトは_MY_NUMBER_を除外(self) -> None:
        v = InMemoryVault()
        assert v.excluded_types == frozenset({"MY_NUMBER"})

    def test_MY_NUMBER_は_None_を返す(self) -> None:
        v = InMemoryVault()
        assert v.assign("MY_NUMBER", "123456789012") is None

    def test_除外_type_は対応表に残らない(self) -> None:
        v = InMemoryVault()
        v.assign("MY_NUMBER", "123456789012")
        assert v.restore("<MY_NUMBER_1>") == "<MY_NUMBER_1>"
        assert v.get("<MY_NUMBER_1>") is None

    def test_カスタム除外集合(self) -> None:
        v = InMemoryVault(excluded_types=["EMAIL", "CREDIT_CARD"])
        assert v.assign("EMAIL", "x@y.z") is None
        assert v.assign("CREDIT_CARD", "4111111111111111") is None
        # MY_NUMBER はもう除外されない（明示的に上書きされた）
        assert v.assign("MY_NUMBER", "123456789012") == "<MY_NUMBER_1>"

    def test_空集合の除外指定_はデフォルトを無効化(self) -> None:
        v = InMemoryVault(excluded_types=[])
        assert v.excluded_types == frozenset()
        assert v.assign("MY_NUMBER", "123456789012") == "<MY_NUMBER_1>"


class TestGet:
    def test_登録済み_placeholder(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.get("<PERSON_1>") == "田中"

    def test_未登録は_None(self) -> None:
        v = InMemoryVault()
        assert v.get("<UNKNOWN_1>") is None


class TestRestore:
    def test_単一_placeholder_を復元(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.restore("<PERSON_1>さん、こんにちは") == "田中さん、こんにちは"

    def test_複数_placeholder_を復元(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        v.assign("PERSON", "佐藤")
        assert v.restore("<PERSON_1>と<PERSON_2>") == "田中と佐藤"

    def test_未登録_placeholder_は素通し(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.restore("<PERSON_1>と<UNKNOWN_1>") == "田中と<UNKNOWN_1>"

    def test_番号が二桁以上でも誤置換しない(self) -> None:
        v = InMemoryVault()
        for i in range(1, 12):  # PERSON_1 ... PERSON_11
            v.assign("PERSON", f"name_{i}")
        # PERSON_11 の置換が PERSON_1 + "1" として誤マッチしないこと
        restored = v.restore("<PERSON_11>")
        assert restored == "name_11"

    def test_placeholder_を含まないテキストは変更なし(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.restore("変更なしのテキスト") == "変更なしのテキスト"

    def test_空のバウルトは何も置換しない(self) -> None:
        v = InMemoryVault()
        assert v.restore("<PERSON_1>") == "<PERSON_1>"


class TestVaultProtocol:
    """InMemoryVault が Vault プロトコルを満たすことの確認."""

    def test_InMemoryVault_は_Vault_として扱える(self) -> None:
        from fuseji.vault import Vault

        v: Vault = InMemoryVault()
        v.assign("PERSON", "山田")
        assert v.get("<PERSON_1>") == "山田"
        assert v.restore("<PERSON_1>") == "山田"
