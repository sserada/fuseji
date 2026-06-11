"""strategies.py のテスト."""

from __future__ import annotations

import hashlib

import pytest

from fuseji.strategies import Hash, Placeholder, Redact

from .conftest import make_entity as _entity


class TestPlaceholder:
    def test_単一エンティティ(self) -> None:
        text = "メールは taro@example.com です"
        entities = [_entity("EMAIL", "taro@example.com", 5, 21)]
        masked, mapping = Placeholder().mask(text, entities)
        assert masked == "メールは <EMAIL_1> です"
        assert mapping == {"<EMAIL_1>": "taro@example.com"}

    def test_異なる表層形_は別番号(self) -> None:
        text = "田中さんと佐藤さん"
        entities = [
            _entity("PERSON", "田中", 0, 2),
            _entity("PERSON", "佐藤", 5, 7),
        ]
        masked, mapping = Placeholder().mask(text, entities)
        assert masked == "<PERSON_1>さんと<PERSON_2>さん"
        assert mapping == {"<PERSON_1>": "田中", "<PERSON_2>": "佐藤"}

    def test_同一表層形_は同一番号(self) -> None:
        text = "田中さん、田中部長"
        entities = [
            _entity("PERSON", "田中", 0, 2),
            _entity("PERSON", "田中", 5, 7),
        ]
        masked, mapping = Placeholder().mask(text, entities)
        assert masked == "<PERSON_1>さん、<PERSON_1>部長"
        assert mapping == {"<PERSON_1>": "田中"}

    def test_異なる_type_は別番号系列(self) -> None:
        text = "山田 taro@example.com"
        entities = [
            _entity("PERSON", "山田", 0, 2),
            _entity("EMAIL", "taro@example.com", 3, 19),
        ]
        masked, mapping = Placeholder().mask(text, entities)
        assert masked == "<PERSON_1> <EMAIL_1>"
        assert mapping == {"<PERSON_1>": "山田", "<EMAIL_1>": "taro@example.com"}

    def test_番号は元テキストの出現順(self) -> None:
        # 入力順を逆にしても、付番は元テキスト位置順
        text = "Aさん、Bさん、Cさん"
        entities = [
            _entity("PERSON", "C", 8, 9),
            _entity("PERSON", "A", 0, 1),
            _entity("PERSON", "B", 4, 5),
        ]
        masked, mapping = Placeholder().mask(text, entities)
        assert masked == "<PERSON_1>さん、<PERSON_2>さん、<PERSON_3>さん"
        assert mapping == {"<PERSON_1>": "A", "<PERSON_2>": "B", "<PERSON_3>": "C"}

    def test_空_entities(self) -> None:
        masked, mapping = Placeholder().mask("変更なし", [])
        assert masked == "変更なし"
        assert mapping == {}

    def test_絵文字を含むテキスト(self) -> None:
        text = "👋 taro@example.com 👋"
        # コードポイント単位で 👋 は 1 文字
        entities = [_entity("EMAIL", "taro@example.com", 2, 18)]
        masked, _ = Placeholder().mask(text, entities)
        assert masked == "👋 <EMAIL_1> 👋"


class TestRedact:
    def test_デフォルト置換文字列(self) -> None:
        text = "電話は 090-1234-5678 まで"
        entities = [_entity("JP_PHONE", "090-1234-5678", 4, 17)]
        masked, mapping = Redact().mask(text, entities)
        assert masked == "電話は [REDACTED] まで"
        assert mapping == {}

    def test_カスタム置換文字列(self) -> None:
        text = "abc def"
        entities = [_entity("X", "def", 4, 7)]
        masked, _ = Redact(replacement="***").mask(text, entities)
        assert masked == "abc ***"

    def test_複数置換(self) -> None:
        text = "aXbYc"
        entities = [_entity("T", "X", 1, 2), _entity("T", "Y", 3, 4)]
        masked, mapping = Redact(replacement="_").mask(text, entities)
        assert masked == "a_b_c"
        assert mapping == {}

    def test_空_entities(self) -> None:
        masked, mapping = Redact().mask("そのまま", [])
        assert masked == "そのまま"
        assert mapping == {}


class TestHash:
    def test_単一エンティティ(self) -> None:
        text = "電話は 090-1234-5678 まで"
        entities = [_entity("JP_PHONE", "090-1234-5678", 4, 17)]
        masked, mapping = Hash(length=8).mask(text, entities)
        expected = hashlib.sha256(b"090-1234-5678").hexdigest()[:8]
        assert masked == f"電話は {expected} まで"
        assert mapping == {expected: "090-1234-5678"}

    def test_同一表層形_は同一ハッシュ(self) -> None:
        text = "田中田中"
        entities = [_entity("PERSON", "田中", 0, 2), _entity("PERSON", "田中", 2, 4)]
        masked, mapping = Hash().mask(text, entities)
        expected = hashlib.sha256("田中".encode()).hexdigest()[:8]
        assert masked == f"{expected}{expected}"
        assert mapping == {expected: "田中"}

    def test_異なる表層形_は異なるハッシュ(self) -> None:
        text = "田中佐藤"
        entities = [_entity("PERSON", "田中", 0, 2), _entity("PERSON", "佐藤", 2, 4)]
        _, mapping = Hash().mask(text, entities)
        assert len(mapping) == 2
        assert "田中" in mapping.values()
        assert "佐藤" in mapping.values()

    def test_決定性_同じ入力で同じ出力(self) -> None:
        text = "x@y.z"
        entities = [_entity("EMAIL", "x@y.z", 0, 5)]
        m1, _ = Hash().mask(text, entities)
        m2, _ = Hash().mask(text, entities)
        assert m1 == m2

    def test_length_指定(self) -> None:
        text = "x@y.z"
        entities = [_entity("EMAIL", "x@y.z", 0, 5)]
        masked, _ = Hash(length=16).mask(text, entities)
        # マスク後の長さ = ハッシュ長
        assert len(masked) == 16

    @pytest.mark.parametrize("length", [0, -1, 65, 100])
    def test_length_範囲外は拒否(self, length: int) -> None:
        with pytest.raises(ValueError, match="length"):
            Hash(length=length)

    def test_空_entities(self) -> None:
        masked, mapping = Hash().mask("そのまま", [])
        assert masked == "そのまま"
        assert mapping == {}
