"""コア型定義 — Entity と MaskResult."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .exceptions import InvalidEntityError

# 空 mapping のシングルトン。`MaskResult.mapping` のデフォルトに使い、
# `field(default_factory=dict)` で毎回 mutable dict を生成するコストを排除する。
# 型は `Mapping[str, str]`（読み取り専用契約）なので、共有しても安全。
_EMPTY_MAPPING: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Entity:
    """検出された PII エンティティ。

    属性:
        type: エンティティ種別（例: ``"MY_NUMBER"``, ``"JP_PHONE_NUMBER"``）
        text: マッチした表層形
        start: 元テキストへのコードポイント開始オフセット（包含）
        end: 元テキストへのコードポイント終端オフセット（除外）
        score: 信頼度 0.0–1.0
        recognizer: 発火した認識器の識別名
    """

    type: str
    text: str
    start: int
    end: int
    score: float
    recognizer: str

    def __post_init__(self) -> None:
        if self.start < 0:
            raise InvalidEntityError(f"start は非負である必要がある: {self.start}")
        if self.end < self.start:
            raise InvalidEntityError(
                f"end は start 以上である必要がある: start={self.start}, end={self.end}"
            )
        if not 0.0 <= self.score <= 1.0:
            raise InvalidEntityError(f"score は 0.0–1.0 の範囲: {self.score}")


@dataclass(frozen=True, slots=True)
class MaskResult:
    """マスキング処理の結果。

    属性:
        text: マスク済みテキスト
        entities: 検出された全エンティティ（順序は元テキストの位置順）
        mapping: プレースホルダー → 元テキストの対応表（Vault または戦略が出力した場合のみ非空）
    """

    text: str
    entities: tuple[Entity, ...]
    mapping: Mapping[str, str] = field(default=_EMPTY_MAPPING)
