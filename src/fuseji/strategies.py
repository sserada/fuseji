"""マスキング戦略 — MaskStrategy プロトコルと Placeholder / Redact / Hash / VaultStrategy 実装."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .exceptions import InvalidConfigError
from .types import Entity

if TYPE_CHECKING:
    from .vault import Vault


class MaskStrategy(Protocol):
    """マスキング戦略のプロトコル。

    `entities` は `text` 内のオーバーラップしない範囲を指す前提。
    （オーバーラップ解決は Masker エンジンの責任。）
    戻り値は (マスク済みテキスト, placeholder → 元テキストの対応表)。
    対応表が不要な戦略は空 dict を返す。
    """

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]: ...


def _replace_spans(text: str, replacements: list[tuple[int, int, str]]) -> str:
    """指定範囲を 1 パスで置換して新しい文字列を返す。

    `replacements` は ``(start, end, substitute)`` のリスト。範囲はオーバー
    ラップしない前提（Masker のオーバーラップ解決後に呼ばれる）。

    文字列の繰り返しスライス再構築は O(k·n) になるため、segment list で
    1 パスにまとめて O(n+k) で完結させる。
    """
    if not replacements:
        return text
    out: list[str] = []
    cursor = 0
    for start, end, sub in sorted(replacements, key=lambda x: x[0]):
        out.append(text[cursor:start])
        out.append(sub)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


@dataclass(frozen=True, slots=True)
class Placeholder:
    """`<TYPE_N>` 形式のプレースホルダーで置換する戦略。

    同一表層形には同一番号を振る。番号は entity type ごとに独立。
    例: `<PERSON_1>`, `<PERSON_2>`, `<EMAIL_1>`。

    Example:
        >>> from fuseji import Masker, Placeholder
        >>> Masker(strategy=Placeholder()).mask("a@b.com と c@d.com").text
        '<EMAIL_1> と <EMAIL_2>'
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
    """固定文字列で置換する戦略。対応表は持たない。

    Example:
        >>> from fuseji import Masker, Redact
        >>> Masker(strategy=Redact()).mask("a@b.com").text
        '[REDACTED]'
        >>> Masker(strategy=Redact(replacement="***")).mask("a@b.com").text
        '***'
    """

    replacement: str = "[REDACTED]"

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]:
        replacements = [(e.start, e.end, self.replacement) for e in entities]
        masked = _replace_spans(text, replacements)
        return masked, {}


@dataclass(frozen=True, slots=True)
class VaultStrategy:
    """Vault と連動して復元可能な Placeholder 形式でマスクする戦略。

    各 (type, surface) に対し `vault.assign()` で placeholder を取得する。
    同一 surface は vault のライフタイムに渡って同一 placeholder。
    excluded type（`vault.assign` が None を返す）は番号なし `<TYPE>` 形式で
    マスクし、`mapping` には残さない（復元不可、番号法対応）。

    `Masker(vault=...)` 指定時に自動で組み立てられるため、通常はユーザーが
    直接インスタンス化する必要はない。
    """

    vault: Vault

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]:
        if not entities:
            return text, {}
        # ユニーク化した (type, surface) を 1 回の assign_many で一括採番し、
        # k 回の lock 取得を 1 回に縮約する（#97）。同一 surface の重複は
        # mapping の整合性を保つため事前に除去する。
        seen: dict[tuple[str, str], int] = {}
        unique_pairs: list[tuple[str, str]] = []
        for e in entities:
            key = (e.type, e.text)
            if key not in seen:
                seen[key] = len(unique_pairs)
                unique_pairs.append(key)
        assigned = self.vault.assign_many(unique_pairs)
        # (type, surface) → placeholder（excluded type のときは None）
        ph_by_key: dict[tuple[str, str], str | None] = {
            unique_pairs[i]: assigned[i] for i in range(len(unique_pairs))
        }
        replacements: list[tuple[int, int, str]] = []
        mapping: dict[str, str] = {}
        for e in entities:
            ph = ph_by_key[(e.type, e.text)]
            if ph is None:
                ph = f"<{e.type}>"
            else:
                mapping[ph] = e.text
            replacements.append((e.start, e.end, ph))
        return _replace_spans(text, replacements), mapping


@dataclass(frozen=True, slots=True)
class Hash:
    """SHA256 ハッシュの先頭 N 文字（hex）で置換する戦略。

    同一表層形は同一ハッシュとなり、ログ上で分析しつつ原文は伏せられる。

    **セキュリティ**:
    - `length` のデフォルトは 16 文字 (64bit)。8 以下は低エントロピー PII
      （email/電話番号）に対するレインボー攻撃で完全逆引きされうるため非推奨。
    - 戻り値 `mapping` はデフォルトで **空 dict**。`keep_mapping=True` を
      明示的に指定したときのみ `{hash: 元 surface}` を返す。
      v0.1 のデフォルト挙動（mapping に逆引きテーブル）は PII 漏洩経路
      になりうるため v0.2 で破壊的変更（#82）。

    Example:
        >>> from fuseji import Masker, Hash
        >>> result = Masker(strategy=Hash(length=8)).mask("a@b.com")
        >>> len(result.text)  # 8 文字のハッシュ
        8
        >>> result.mapping  # デフォルトは空（PII を残さない）
        {}
    """

    length: int = 16
    keep_mapping: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.length <= 64:
            raise InvalidConfigError(f"length は 1–64 の範囲: {self.length}")

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]:
        surface_to_hash: dict[str, str] = {}
        for e in entities:
            if e.text not in surface_to_hash:
                digest = hashlib.sha256(e.text.encode("utf-8")).hexdigest()
                surface_to_hash[e.text] = digest[: self.length]

        replacements = [(e.start, e.end, surface_to_hash[e.text]) for e in entities]
        masked = _replace_spans(text, replacements)
        mapping: dict[str, str] = (
            {h: surface for surface, h in surface_to_hash.items()} if self.keep_mapping else {}
        )
        return masked, mapping
