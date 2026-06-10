"""ner/ginza.py のテスト（spaCy + ja_ginza が必要）."""

from __future__ import annotations

import pytest

# GiNZA がインストールされていなければモジュール全体をスキップ
pytest.importorskip("spacy")
pytest.importorskip("ginza")

from fuseji.ner.ginza import GinzaBackend


@pytest.fixture(scope="module")
def backend() -> GinzaBackend:
    """セッション全体で 1 つの GinzaBackend を共有（モデルロード重いため）."""
    return GinzaBackend()


class TestGinzaBackend:
    def test_PERSON_を検出(self, backend: GinzaBackend) -> None:
        entities = list(backend.analyze("山田太郎さんは東京都に住んでいます。"))
        persons = [e for e in entities if e.type == "PERSON"]
        assert len(persons) >= 1
        e = persons[0]
        assert e.text == "山田太郎"
        assert e.start == 0
        assert e.end == 4
        assert e.score == 0.85
        assert e.recognizer == "ginza"

    def test_デフォルトでは_Person_のみ抽出(self, backend: GinzaBackend) -> None:
        entities = list(backend.analyze("山田太郎さんは東京都に住んでいます。"))
        types = {e.type for e in entities}
        assert types == {"PERSON"}

    def test_カスタムラベル指定で他種を抽出(self) -> None:
        backend = GinzaBackend(labels=("Person", "Province", "City"))
        entities = list(backend.analyze("山田太郎さんは東京都新宿区に住んでいます。"))
        types = {e.type for e in entities}
        assert "PERSON" in types
        # GiNZA は Province / City を出す
        assert "PROVINCE" in types or "CITY" in types

    def test_空文字列(self, backend: GinzaBackend) -> None:
        assert list(backend.analyze("")) == []

    def test_オフセットが正しい(self, backend: GinzaBackend) -> None:
        text = "本日は山田太郎さんに会いました。"
        entities = list(backend.analyze(text))
        for e in entities:
            assert text[e.start : e.end] == e.text

    def test_複数の人名を検出(self, backend: GinzaBackend) -> None:
        text = "佐藤さんと田中さんが来ました。"
        entities = list(backend.analyze(text))
        names = {e.text for e in entities}
        assert "佐藤" in names
        assert "田中" in names
