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
