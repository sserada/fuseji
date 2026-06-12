"""types.py のテスト."""

from __future__ import annotations

import pytest

from fuseji.types import Entity, MaskResult


class TestEntity:
    def test_正常生成(self) -> None:
        e = Entity(
            type="EMAIL",
            text="taro@example.com",
            start=3,
            end=19,
            score=0.95,
            recognizer="email",
        )
        assert e.type == "EMAIL"
        assert e.text == "taro@example.com"
        assert e.end - e.start == 16

    def test_frozen_変更不可(self) -> None:
        e = Entity(type="EMAIL", text="x", start=0, end=1, score=1.0, recognizer="email")
        with pytest.raises((AttributeError, TypeError)):
            e.type = "PHONE"  # type: ignore[misc]

    def test_等価性(self) -> None:
        e1 = Entity(type="EMAIL", text="x", start=0, end=1, score=1.0, recognizer="email")
        e2 = Entity(type="EMAIL", text="x", start=0, end=1, score=1.0, recognizer="email")
        assert e1 == e2
        assert hash(e1) == hash(e2)

    def test_start_負数は拒否(self) -> None:
        with pytest.raises(ValueError, match="start"):
            Entity(type="X", text="a", start=-1, end=0, score=0.5, recognizer="r")

    def test_end_が_start_未満は拒否(self) -> None:
        with pytest.raises(ValueError, match="end"):
            Entity(type="X", text="a", start=5, end=3, score=0.5, recognizer="r")

    def test_start_と_end_が等しいのは許容(self) -> None:
        # 空マッチを禁じない（呼び出し側の責任）
        e = Entity(type="X", text="", start=5, end=5, score=0.5, recognizer="r")
        assert e.start == e.end

    @pytest.mark.parametrize("score", [-0.01, 1.01, 2.0, -1.0])
    def test_score_範囲外は拒否(self, score: float) -> None:
        with pytest.raises(ValueError, match="score"):
            Entity(type="X", text="a", start=0, end=1, score=score, recognizer="r")

    @pytest.mark.parametrize("score", [0.0, 0.5, 1.0])
    def test_score_境界値は許容(self, score: float) -> None:
        e = Entity(type="X", text="a", start=0, end=1, score=score, recognizer="r")
        assert e.score == score


class TestEntityRepr:
    """#144: repr に原 PII surface を漏出させないこと."""

    def test_repr_に_原_text_が_含まれない(self) -> None:
        e = Entity(
            type="MY_NUMBER",
            text="123456789018",
            start=0,
            end=12,
            score=0.95,
            recognizer="my_number",
        )
        text = repr(e)
        assert "123456789018" not in text
        # 安全要約のメタ情報は残る
        assert "MY_NUMBER" in text
        assert "len=12" in text
        assert "hash=" in text
        assert "start=0" in text
        assert "end=12" in text
        assert "score=0.95" in text
        assert "my_number" in text

    def test_repr_は_email_も_隠す(self) -> None:
        e = Entity(
            type="EMAIL", text="taro@example.com", start=0, end=16, score=1.0, recognizer="email"
        )
        text = repr(e)
        assert "taro" not in text
        assert "example.com" not in text
        assert "len=16" in text

    def test_repr_は_短い_text_も_要約する(self) -> None:
        # 短いものでも生原文を出さない（部分一致でも漏れる可能性）
        e = Entity(type="X", text="ab", start=0, end=2, score=0.5, recognizer="r")
        text = repr(e)
        assert "'ab'" not in text
        assert "len=2" in text

    def test_同じ_text_の_repr_は_同じ_hash(self) -> None:
        e1 = Entity(type="X", text="abc", start=0, end=3, score=0.5, recognizer="r")
        e2 = Entity(type="X", text="abc", start=10, end=13, score=0.5, recognizer="r")
        # オフセットは異なっても hash は同じ → 同一 surface が再出現したことを debug できる
        import re

        h1 = re.search(r"hash=([0-9a-f]+)", repr(e1))
        h2 = re.search(r"hash=([0-9a-f]+)", repr(e2))
        assert h1 is not None and h2 is not None
        assert h1.group(1) == h2.group(1)

    def test_異なる_text_は_異なる_hash(self) -> None:
        import re

        e1 = Entity(type="X", text="alpha", start=0, end=5, score=0.5, recognizer="r")
        e2 = Entity(type="X", text="beta", start=0, end=4, score=0.5, recognizer="r")
        h1 = re.search(r"hash=([0-9a-f]+)", repr(e1))
        h2 = re.search(r"hash=([0-9a-f]+)", repr(e2))
        assert h1 is not None and h2 is not None
        assert h1.group(1) != h2.group(1)

    def test_unsafe_repr_は_原_text_を_含む(self) -> None:
        e = Entity(
            type="EMAIL", text="taro@example.com", start=0, end=16, score=1.0, recognizer="email"
        )
        text = e.unsafe_repr()
        # opt-in なので生原文を含む
        assert "taro@example.com" in text

    def test_format_string_で_repr_経路でも_PII_が_漏れない(self) -> None:
        # logger.info('%s', entity) や f'{entity}' 経路は str()/repr() を呼ぶ
        e = Entity(
            type="EMAIL", text="taro@example.com", start=0, end=16, score=1.0, recognizer="email"
        )
        assert "taro@example.com" not in f"{e}"
        assert "taro@example.com" not in str(e)


class TestMaskResult:
    def test_デフォルトで空_mapping(self) -> None:
        r = MaskResult(text="hello", entities=())
        assert r.text == "hello"
        assert r.entities == ()
        assert dict(r.mapping) == {}

    def test_mapping_を含めて生成(self) -> None:
        e = Entity(type="EMAIL", text="x@y", start=0, end=3, score=1.0, recognizer="email")
        r = MaskResult(text="<EMAIL_1>", entities=(e,), mapping={"<EMAIL_1>": "x@y"})
        assert r.mapping["<EMAIL_1>"] == "x@y"

    def test_frozen_変更不可(self) -> None:
        r = MaskResult(text="x", entities=())
        with pytest.raises((AttributeError, TypeError)):
            r.text = "y"  # type: ignore[misc]

    def test_entities_は_tuple(self) -> None:
        r = MaskResult(text="x", entities=())
        assert isinstance(r.entities, tuple)


class TestMaskResultRepr:
    """#144: repr で entities / mapping の中身を漏出させないこと."""

    def test_repr_に_原_text_は_含まれない(self) -> None:
        e = Entity(
            type="EMAIL", text="taro@example.com", start=0, end=16, score=1.0, recognizer="email"
        )
        r = MaskResult(
            text="メール: <EMAIL_1>",
            entities=(e,),
            mapping={"<EMAIL_1>": "taro@example.com"},
        )
        text = repr(r)
        assert "taro@example.com" not in text
        # サマリ情報は残る
        assert "count=1" in text
        # mask 済み text の中身も出さない (placeholder 推測経路の最小化)
        assert "EMAIL_1" not in text

    def test_repr_に_mapping_の_中身が_含まれない(self) -> None:
        e = Entity(
            type="MY_NUMBER",
            text="123456789018",
            start=0,
            end=12,
            score=0.95,
            recognizer="my_number",
        )
        r = MaskResult(
            text="<MY_NUMBER_1>",
            entities=(e,),
            mapping={"<MY_NUMBER_1>": "123456789018"},
        )
        text = repr(r)
        assert "123456789018" not in text

    def test_repr_は_件数を返す(self) -> None:
        r = MaskResult(text="hello", entities=())
        text = repr(r)
        assert "count=0" in text
        assert "len=5" in text
