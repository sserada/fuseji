"""共通テストヘルパ・フィクスチャ。

複数のテストファイルで重複していた `_entity` ヘルパを `make_entity` として集約する。
"""

from __future__ import annotations

from fuseji.types import Entity


def make_entity(
    type_: str,
    text: str,
    start: int,
    end: int,
    score: float = 1.0,
    recognizer: str = "test",
) -> Entity:
    """テスト用に Entity を簡潔に作るファクトリ。

    各テストでデフォルト値（score=1.0, recognizer="test"）を都度書くのを省略する。
    """
    return Entity(
        type=type_,
        text=text,
        start=start,
        end=end,
        score=score,
        recognizer=recognizer,
    )
