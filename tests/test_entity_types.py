"""entity_types 定数モジュールのテスト."""

from __future__ import annotations

import fuseji
from fuseji import entity_types


class TestEntityTypeConstants:
    def test_v0_1_の_6_種別が定義されている(self) -> None:
        assert entity_types.EMAIL == "EMAIL"
        assert entity_types.CREDIT_CARD == "CREDIT_CARD"
        assert entity_types.MY_NUMBER == "MY_NUMBER"
        assert entity_types.JP_PHONE_NUMBER == "JP_PHONE_NUMBER"
        assert entity_types.JP_POSTAL_CODE == "JP_POSTAL_CODE"
        assert entity_types.PERSON == "PERSON"

    def test_V0_1_TYPES_は_frozenset(self) -> None:
        assert isinstance(entity_types.V0_1_TYPES, frozenset)
        # 内容比較は set() 化で行う（frozenset と set の == は内容一致で True）
        types_as_set = set(entity_types.V0_1_TYPES)
        assert types_as_set == {
            "EMAIL",
            "CREDIT_CARD",
            "MY_NUMBER",
            "JP_PHONE_NUMBER",
            "JP_POSTAL_CODE",
            "PERSON",
        }

    def test_fuseji_経由でも_import_できる(self) -> None:
        assert fuseji.entity_types is entity_types
        assert fuseji.entity_types.MY_NUMBER == "MY_NUMBER"


class TestUsageScenarios:
    def test_Vault_の_excluded_types_に渡せる(self) -> None:
        from fuseji import InMemoryVault

        vault = InMemoryVault(excluded_types=[entity_types.MY_NUMBER, entity_types.EMAIL])
        assert "MY_NUMBER" in vault.excluded_types
        assert "EMAIL" in vault.excluded_types
        assert vault.assign("EMAIL", "x@y.z") is None  # 除外される

    def test_Entity_type_との比較が文字列のまま動く(self) -> None:
        e = fuseji.Entity(
            type=entity_types.EMAIL,
            text="x@y.z",
            start=0,
            end=5,
            score=1.0,
            recognizer="email",
        )
        # 定数を使った type 値が文字列リテラルとも互換
        assert e.type == "EMAIL"
        assert e.type == entity_types.EMAIL

    def test_認識器が出す_type_と_V0_1_TYPES_が一致する(self) -> None:
        """default_recognizers + NER が出力する種別は V0_1_TYPES に含まれる."""
        from fuseji.recognizers.base import default_recognizers

        recognized_types = {r.entity_type for r in default_recognizers()}
        # PERSON は GiNZA NER でのみ出るので除く
        non_ner_types = entity_types.V0_1_TYPES - {entity_types.PERSON}
        assert recognized_types == non_ner_types
