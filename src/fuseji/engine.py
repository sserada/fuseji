"""Masker エンジン — 認識器・NER を統合し、戦略でテキストをマスクする."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .recognizers.base import default_recognizers
from .strategies import Placeholder
from .types import Entity, MaskResult

if TYPE_CHECKING:
    from .ner.base import NerBackend
    from .recognizers.base import Recognizer
    from .strategies import MaskStrategy
    from .vault import Vault


class Masker:
    """fuseji の中核クラス。

    認識器（正規表現/checksum）と NER バックエンドを統合し、検出した
    PII エンティティを戦略でマスクする。Vault が指定された場合は復元可能な
    Placeholder 形式で常にマスクし、戦略指定は無視される。

    Args:
        recognizers: 使用する認識器。`None` で v0.1 のデフォルトセット。
        ner: NER バックエンド（GiNZA 等）。`None` で NER 無効。
        strategy: マスキング戦略（Placeholder/Redact/Hash）。Vault 指定時は無視。
        threshold: このスコア未満のエンティティは除外する。recall 重視で 0.4。
        vault: 仮名化バウルト。指定すると Placeholder 形式で必ずマスクし、
            mapping を vault に蓄積する。同一表層形は同一 placeholder。
    """

    def __init__(
        self,
        recognizers: Sequence[Recognizer] | None = None,
        ner: NerBackend | None = None,
        strategy: MaskStrategy | None = None,
        threshold: float = 0.4,
        vault: Vault | None = None,
    ) -> None:
        self._recognizers: tuple[Recognizer, ...] = (
            tuple(recognizers) if recognizers is not None else default_recognizers()
        )
        self._ner = ner
        self._strategy: MaskStrategy = strategy if strategy is not None else Placeholder()
        self._threshold = threshold
        self._vault = vault

    def detect(self, text: str) -> tuple[Entity, ...]:
        """テキストから PII エンティティを検出し、threshold で絞り込んだ後、
        オーバーラップをスコア優先で解決して返す。"""
        raw: list[Entity] = []
        for r in self._recognizers:
            raw.extend(r.analyze(text))
        if self._ner is not None:
            raw.extend(self._ner.analyze(text))
        filtered = [e for e in raw if e.score >= self._threshold]
        return tuple(_resolve_overlaps(filtered))

    def mask(self, text: str) -> MaskResult:
        """テキストをマスクして MaskResult を返す。"""
        entities = self.detect(text)
        masked_text: str
        mapping: Mapping[str, str]
        if self._vault is not None:
            masked_text, mapping = _mask_with_vault(text, entities, self._vault)
        else:
            masked_text, mapping = self._strategy.mask(text, entities)
        return MaskResult(text=masked_text, entities=entities, mapping=mapping)


def _resolve_overlaps(entities: Sequence[Entity]) -> list[Entity]:
    """オーバーラップするエンティティをスコア優先で解決する。

    優先順位: スコア降順 → 長い span 優先 → 開始位置昇順。
    採用済み span と重ならないものから順に採用し、最後に元テキスト位置順で
    並べ直して返す。
    """
    ordered = sorted(entities, key=lambda e: (-e.score, -(e.end - e.start), e.start))
    accepted: list[Entity] = []
    spans: list[tuple[int, int]] = []
    for e in ordered:
        if any(not (e.end <= s or e.start >= ee) for s, ee in spans):
            continue
        accepted.append(e)
        spans.append((e.start, e.end))
    return sorted(accepted, key=lambda e: e.start)


def _mask_with_vault(
    text: str, entities: Sequence[Entity], vault: Vault
) -> tuple[str, dict[str, str]]:
    """vault を使ってエンティティをマスクし、(masked_text, mapping) を返す。

    excluded type（vault.assign が None を返す）の場合は番号なしの
    `<TYPE>` 形式でマスクし、mapping には残さない（復元不可）。
    """
    replacements: list[tuple[int, int, str]] = []
    mapping: dict[str, str] = {}
    for e in entities:
        ph = vault.assign(e.type, e.text)
        if ph is None:
            ph = f"<{e.type}>"
        else:
            mapping[ph] = e.text
        replacements.append((e.start, e.end, ph))

    result = text
    for start, end, sub in sorted(replacements, key=lambda x: x[0], reverse=True):
        result = result[:start] + sub + result[end:]
    return result, mapping
