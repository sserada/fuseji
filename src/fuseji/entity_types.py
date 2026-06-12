"""エンティティ種別の定数モジュール。

ハードコードされた文字列リテラル（``"EMAIL"`` 等）の代わりに、
タイプセーフな定数として利用できる。

Example:
    >>> from fuseji import InMemoryVault, entity_types
    >>> vault = InMemoryVault(excluded_types=[entity_types.MY_NUMBER, entity_types.EMAIL])
    >>> sorted(vault.excluded_types)
    ['EMAIL', 'MY_NUMBER']

定数は文字列そのもの（``str``）。Entity.type と直接比較できる。

v0.2 以降で追加されるエンティティ種別（JP_ADDRESS、CORPORATE_NUMBER 等）も
本モジュールに集約する予定。
"""

from __future__ import annotations

#: メールアドレス
EMAIL: str = "EMAIL"
#: クレジットカード番号（Luhn 検証通過）
CREDIT_CARD: str = "CREDIT_CARD"
#: マイナンバー（個人番号 12 桁）
MY_NUMBER: str = "MY_NUMBER"
#: 法人番号（13 桁、国税庁が公開、v0.3 で opt-in 認識器を追加 #126）
CORPORATE_NUMBER: str = "CORPORATE_NUMBER"
#: 日本の住所（都道府県 prefix + 市区町村 + 番地、v0.3 で opt-in 認識器を追加 #127）
JP_ADDRESS: str = "JP_ADDRESS"
#: 日本の電話番号（携帯・固定・フリーダイヤル・ナビダイヤル）
JP_PHONE_NUMBER: str = "JP_PHONE_NUMBER"
#: 日本の郵便番号
JP_POSTAL_CODE: str = "JP_POSTAL_CODE"
#: 人名（GiNZA バックエンドが出力）
PERSON: str = "PERSON"

#: v0.1 で組み込み recognizers が出力する種別の全集合（NER 含む）
V0_1_TYPES: frozenset[str] = frozenset(
    {EMAIL, CREDIT_CARD, MY_NUMBER, JP_PHONE_NUMBER, JP_POSTAL_CODE, PERSON}
)

__all__ = [
    "CORPORATE_NUMBER",
    "CREDIT_CARD",
    "EMAIL",
    "JP_ADDRESS",
    "JP_PHONE_NUMBER",
    "JP_POSTAL_CODE",
    "MY_NUMBER",
    "PERSON",
    "V0_1_TYPES",
]
