"""Masker エンジン — 認識器・NER を統合し、戦略でテキストをマスクする."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .recognizers.base import default_recognizers, normalize
from .strategies import Placeholder, VaultStrategy
from .types import Entity, MaskResult

if TYPE_CHECKING:
    from .ner.base import NerBackend
    from .recognizers.base import Recognizer
    from .strategies import MaskStrategy
    from .vault import Vault

# mask_json の再帰深度制限。深いネストでスタック消費を防ぐための fail-closed 値。
DEFAULT_MAX_JSON_DEPTH: int = 100
# 深度超過時に返す固定 placeholder。fail-closed として原データを返さない。
_TOO_DEEP_PLACEHOLDER: str = "[fuseji: too deep]"


class Masker:
    """fuseji の中核クラス。

    認識器（正規表現/checksum）と NER バックエンドを統合し、検出した
    PII エンティティを戦略でマスクする。

    Args:
        recognizers: 使用する認識器。`None` で v0.1 のデフォルトセット。
        ner: NER バックエンド（GiNZA 等）。`None` で NER 無効。
        strategy: マスキング戦略（Placeholder/Redact/Hash）。Vault 指定時は
            `VaultStrategy` で自動的に置き換えられ、本引数は無視される
            （両者を同時指定すると `UserWarning` が発行される）。
        threshold: このスコア未満のエンティティは除外する。recall 重視で 0.4。
        vault: 仮名化バウルト。指定時は `VaultStrategy(vault=vault)` が
            内部戦略として使われ、同一表層形は同一 placeholder。excluded type
            は番号なし `<TYPE>` 形式でマスクし、mapping に残らない。
        max_json_depth: `mask_json` の再帰深度上限。超過時は fail-closed で
            `"[fuseji: too deep]"` に置換される。

    Example:
        基本的な使い方:

        >>> from fuseji import Masker
        >>> masker = Masker()
        >>> result = masker.mask("メール: taro@example.co.jp、電話 090-1234-5678")
        >>> print(result.text)
        メール: <EMAIL_1>、電話 <JP_PHONE_NUMBER_1>

        Redact 戦略で固定文字列に:

        >>> from fuseji import Masker, Redact
        >>> masker = Masker(strategy=Redact())
        >>> masker.mask("a@b.com").text
        '[REDACTED]'

        Vault で復元可能なマスキング:

        >>> from fuseji import Masker, InMemoryVault
        >>> vault = InMemoryVault()
        >>> masker = Masker(vault=vault)
        >>> r = masker.mask("a@b.com への返信")
        >>> vault.restore(r.text)
        'a@b.com への返信'
    """

    def __init__(
        self,
        recognizers: Sequence[Recognizer] | None = None,
        ner: NerBackend | None = None,
        strategy: MaskStrategy | None = None,
        threshold: float = 0.4,
        vault: Vault | None = None,
        max_json_depth: int = DEFAULT_MAX_JSON_DEPTH,
    ) -> None:
        self._recognizers: tuple[Recognizer, ...] = (
            tuple(recognizers) if recognizers is not None else default_recognizers()
        )
        self._ner = ner
        # vault があれば VaultStrategy で吸収し、戦略経路を単一化する。
        # strategy 引数は vault と排他（vault 優先、strategy 無視）。
        if vault is not None:
            if strategy is not None:
                warnings.warn(
                    "Masker: strategy と vault が同時指定されました。"
                    "vault を優先して strategy は無視されます。"
                    "両者を明確に分離するには Masker(vault=...) または "
                    "Masker(strategy=...) のいずれか一方のみ指定してください。",
                    UserWarning,
                    stacklevel=2,
                )
            self._strategy: MaskStrategy = VaultStrategy(vault=vault)
        else:
            self._strategy = strategy if strategy is not None else Placeholder()
        self._threshold = threshold
        self._max_json_depth = max_json_depth

    def detect(self, text: str) -> tuple[Entity, ...]:
        """テキストから PII エンティティを検出し、threshold で絞り込んだ後、
        オーバーラップをスコア優先で解決して返す。

        Example:
            >>> from fuseji import Masker
            >>> entities = Masker().detect("メール a@b.com 電話 090-1234-5678")
            >>> sorted({e.type for e in entities})
            ['EMAIL', 'JP_PHONE_NUMBER']
        """
        raw: list[Entity] = []
        # Masker 層で normalize を 1 回計算し、各認識器に渡す（v0.2 Protocol 要件）。
        normalized = normalize(text)
        for r in self._recognizers:
            raw.extend(r.analyze(text, normalized=normalized))
        if self._ner is not None:
            raw.extend(self._ner.analyze(text))
        filtered = [e for e in raw if e.score >= self._threshold]
        return tuple(_resolve_overlaps(filtered))

    def mask(self, text: str) -> MaskResult:
        """テキストをマスクして MaskResult を返す。"""
        entities = self.detect(text)
        masked_text, mapping = self._strategy.mask(text, entities)
        return MaskResult(text=masked_text, entities=entities, mapping=mapping)

    def mask_json(self, data: Any) -> Any:
        """JSON 互換のデータ構造を再帰的にマスクして返す。

        対象: str（mask() を適用）, dict（値のみ再帰）, list/tuple（要素を再帰）。
        その他の型（int, float, bool, None など）は素通し。

        辞書のキーは PII を含まない前提で、値のみマスクする。

        ネスト深度が `max_json_depth`（デフォルト 100）を超えた要素は
        fail-closed で固定文字列 `"[fuseji: too deep]"` に置換される。
        スタック消費や無限再帰由来の DoS を抑止する。

        Example:
            >>> from fuseji import Masker
            >>> result = Masker().mask_json({"email": "a@b.com", "user": "山田"})
            >>> result["email"]
            '<EMAIL_1>'
            >>> result["user"]
            '山田'
        """
        return self._mask_value(data, depth=0)

    def _mask_value(self, data: Any, *, depth: int) -> Any:
        if depth > self._max_json_depth:
            return _TOO_DEEP_PLACEHOLDER
        if isinstance(data, str):
            return self.mask(data).text
        if isinstance(data, dict):
            return {k: self._mask_value(v, depth=depth + 1) for k, v in data.items()}
        if isinstance(data, list):
            return [self._mask_value(v, depth=depth + 1) for v in data]
        if isinstance(data, tuple):
            return tuple(self._mask_value(v, depth=depth + 1) for v in data)
        return data


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
