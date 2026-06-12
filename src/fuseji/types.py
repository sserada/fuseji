"""コア型定義 — Entity と MaskResult."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .exceptions import InvalidEntityError

# 空 mapping のシングルトン。`MaskResult.mapping` のデフォルトに使い、
# `field(default_factory=dict)` で毎回 mutable dict を生成するコストを排除する。
# 型は `Mapping[str, str]`（読み取り専用契約）なので、共有しても安全。
_EMPTY_MAPPING: Mapping[str, str] = MappingProxyType({})

# repr の `hash=` フィールドに使う surface 要約のプレフィックス長 (#144)。
# 8 文字 (32bit) で別 surface との衝突確率は十分低く、かつ短すぎず
# debug log の grep に使える。surface 復元には十分すぎる程の情報量はない。
_REPR_HASH_LEN: int = 8


def _safe_surface_summary(text: str) -> str:
    """surface を repr 用に PII safe な要約に変換 (#144).

    `<len=N hash=XXXXXXXX>` の形式。`len` は元 surface の長さ (コードポイント数)、
    `hash` は SHA256 prefix 8 文字。同じ surface は同じ要約になるため debug 用途
    で 1 マッチを追跡できるが、surface 原本の復元はできない。
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:_REPR_HASH_LEN]
    return f"len={len(text)} hash={digest}"


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

    Note:
        ``repr(entity)`` は PII safe な要約のみ返す (#144)。
        生 ``text`` フィールドへのアクセスは属性参照経由でのみ可能で、
        ログ・traceback・pytest dump で偶発的に PII が刻まれない。
        デバッグで生表層形が必要な場合は ``entity.unsafe_repr()`` を opt-in。
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

    def __repr__(self) -> str:
        # PII safe な要約 (#144)。原 text は出力しない。
        return (
            f"Entity(type={self.type!r}, "
            f"text=<{_safe_surface_summary(self.text)}>, "
            f"start={self.start}, end={self.end}, "
            f"score={self.score}, recognizer={self.recognizer!r})"
        )

    def unsafe_repr(self) -> str:
        """デバッグ用に原 ``text`` を含む repr を返す (#144, opt-in).

        **警告**: ログ / traceback / 永続化に渡してはいけない。
        本メソッドの呼び出し元は PII を露出させる責任を負う。
        """
        return (
            f"Entity(type={self.type!r}, text={self.text!r}, "
            f"start={self.start}, end={self.end}, "
            f"score={self.score}, recognizer={self.recognizer!r})"
        )


@dataclass(frozen=True, slots=True)
class MaskResult:
    """マスキング処理の結果。

    属性:
        text: マスク済みテキスト
        entities: 検出された全エンティティ（順序は元テキストの位置順）
        mapping: プレースホルダー → 元テキストの対応表（Vault または戦略が出力した場合のみ非空）

    Note:
        ``repr(result)`` は PII safe な要約のみ返す (#144)。``text`` フィールドは
        マスク済みのため安全だが、``entities`` と ``mapping`` は原 PII を含むため
        件数と長さのみを示し、中身は出力しない。
    """

    text: str
    entities: tuple[Entity, ...]
    mapping: Mapping[str, str] = field(default=_EMPTY_MAPPING)

    def __repr__(self) -> str:
        # PII safe な要約 (#144)。entities / mapping の中身は出さない。
        # text はマスク済みのため、長さのみ示し中身は出力しない (Vault placeholder や
        # mapping key からの逆引きでの推測経路を最小化)。
        return (
            f"MaskResult(text=<len={len(self.text)}>, "
            f"entities=<count={len(self.entities)}>, "
            f"mapping=<count={len(self.mapping)}>)"
        )
