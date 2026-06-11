"""GiNZA バックエンド（PERSON 検出）."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING

from ..entity_types import PERSON
from ..types import Entity

if TYPE_CHECKING:
    from spacy.language import Language

# GiNZA が PERSON 検出に使うラベル名（GiNZA 独自表記、fuseji の
# `entity_types.PERSON` とは別物）。spaCy / GiNZA のバージョンが上がって
# 表記がブレた場合、ここを変えるだけで吸収できる。
_GINZA_PERSON_LABEL: str = "Person"
# GiNZA は OntoNotes ではなく GSK 風の独自ラベルを返す。
# v0.1 では「Person」だけを採用し、他のラベル（Title_Other, Province 等）は
# 利用側で明示的に指定したいときのみ拾う。
_DEFAULT_LABELS: tuple[str, ...] = (_GINZA_PERSON_LABEL,)


class GinzaBackend:
    """GiNZA (spaCy + ja_ginza) ベースの NER バックエンド。

    `labels` で抽出する GiNZA ラベルを指定する。デフォルトは ``("Person",)``。
    抽出した Entity の type フィールドは ``Person`` を慣用名 ``PERSON`` に
    マップし、その他のラベルは大文字化してそのまま使う。

    `[ginza]` extra 経由でのみインストール可能（``pip install fuseji[ginza]``）。
    """

    def __init__(
        self,
        labels: Iterable[str] | None = None,
        model_name: str = "ja_ginza",
        score: float = 0.85,
    ) -> None:
        try:
            import spacy
        except ImportError as e:
            msg = (
                "GinzaBackend を使うには spaCy と ja_ginza が必要です。"
                "`pip install fuseji[ginza]` でインストールしてください。"
            )
            raise ImportError(msg) from e

        self._labels: set[str] = set(labels) if labels is not None else set(_DEFAULT_LABELS)
        self._score = score
        # GiNZA 5.2 系の compound_splitter は新版 spaCy で設定不整合を起こすため除外
        self._nlp: Language = spacy.load(model_name, exclude=["compound_splitter"])

    @property
    def labels(self) -> frozenset[str]:
        return frozenset(self._labels)

    def analyze(self, text: str) -> Iterator[Entity]:
        if not text:
            return
        doc = self._nlp(text)
        for ent in doc.ents:
            if ent.label_ not in self._labels:
                continue
            # GiNZA の "Person" → 慣用名 PERSON 定数に正規化
            type_ = PERSON if ent.label_ == _GINZA_PERSON_LABEL else ent.label_.upper()
            yield Entity(
                type=type_,
                text=ent.text,
                start=ent.start_char,
                end=ent.end_char,
                score=self._score,
                recognizer="ginza",
            )
