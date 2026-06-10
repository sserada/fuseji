"""マスキング戦略 — MaskStrategy プロトコルと Placeholder / Redact / Hash 実装."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .types import Entity


class MaskStrategy(Protocol):
    """マスキング戦略のプロトコル。

    `entities` は `text` 内のオーバーラップしない範囲を指す前提。
    （オーバーラップ解決は Masker エンジンの責任。）
    戻り値は (マスク済みテキスト, placeholder → 元テキストの対応表)。
    対応表が不要な戦略は空 dict を返す。
    """

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]: ...


def _replace_spans(text: str, replacements: list[tuple[int, int, str]]) -> str:
    """指定範囲を後ろから置換してオフセットずれを防ぐ."""
    result = text
    for start, end, sub in sorted(replacements, key=lambda x: x[0], reverse=True):
        result = result[:start] + sub + result[end:]
    return result


@dataclass(frozen=True, slots=True)
class Placeholder:
    """`<TYPE_N>` 形式のプレースホルダーで置換する戦略。

    同一表層形には同一番号を振る。番号は entity type ごとに独立。
    例: `<PERSON_1>`, `<PERSON_2>`, `<EMAIL_1>`。
    """

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]:
        counters: dict[str, int] = {}
        # (type, surface) → placeholder の割当
        assigned: dict[tuple[str, str], str] = {}
        # 元テキスト順で番号を振る
        for e in sorted(entities, key=lambda x: x.start):
            key = (e.type, e.text)
            if key not in assigned:
                counters[e.type] = counters.get(e.type, 0) + 1
                assigned[key] = f"<{e.type}_{counters[e.type]}>"

        replacements = [(e.start, e.end, assigned[(e.type, e.text)]) for e in entities]
        masked = _replace_spans(text, replacements)
        mapping = {placeholder: surface for (_, surface), placeholder in assigned.items()}
        return masked, mapping


@dataclass(frozen=True, slots=True)
class Redact:
    """固定文字列で置換する戦略。対応表は持たない。"""

    replacement: str = "[REDACTED]"

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]:
        replacements = [(e.start, e.end, self.replacement) for e in entities]
        masked = _replace_spans(text, replacements)
        return masked, {}


@dataclass(frozen=True, slots=True)
class Hash:
    """SHA256 ハッシュの先頭 N 文字（hex）で置換する戦略。

    同一表層形は同一ハッシュとなり、ログ上で分析しつつ原文は伏せられる。
    対応表は hash → 元テキストを持つ（一方向だが既知集合からの逆引きは可能）。
    """

    length: int = 8

    def __post_init__(self) -> None:
        if not 1 <= self.length <= 64:
            raise ValueError(f"length は 1–64 の範囲: {self.length}")

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]:
        surface_to_hash: dict[str, str] = {}
        for e in entities:
            if e.text not in surface_to_hash:
                digest = hashlib.sha256(e.text.encode("utf-8")).hexdigest()
                surface_to_hash[e.text] = digest[: self.length]

        replacements = [(e.start, e.end, surface_to_hash[e.text]) for e in entities]
        masked = _replace_spans(text, replacements)
        mapping = {h: surface for surface, h in surface_to_hash.items()}
        return masked, mapping
