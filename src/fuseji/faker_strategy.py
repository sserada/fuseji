"""Faker 戦略 — PII を架空値に置換 (#128).

LLM オブザーバビリティで「実テキストっぽい形を保ったまま PII を伏せたい」
用途のための戦略。下位互換性のため `[faker]` extra として分離。

設計方針:
- エンティティタイプごとに架空値生成関数をマップ
- 同一 surface には同一架空値を返す決定的モード（context preservation）
- 高センシティビティ type (`MY_NUMBER`, `CREDIT_CARD`, `CORPORATE_NUMBER`) は
  Faker 生成だと fuseji が再検出してしまう or 法令上の扱いが厳しいため
  固定マスク文字列にフォールバック
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .entity_types import (
    CORPORATE_NUMBER,
    CREDIT_CARD,
    EMAIL,
    JP_PHONE_NUMBER,
    JP_POSTAL_CODE,
    MY_NUMBER,
    PERSON,
)
from .exceptions import InvalidConfigError
from .strategies import _replace_spans
from .types import Entity

if TYPE_CHECKING:
    from faker import Faker

# 再検出を避けるため固定マスクにする type 集合（番号法対応 / Luhn 通過の架空 CC を避ける）
_FIXED_MASK_TYPES: frozenset[str] = frozenset({MY_NUMBER, CREDIT_CARD, CORPORATE_NUMBER})
_FIXED_MASK_LABEL: str = "<MASKED>"

# Faker が出さない安全な fictitious format（再検出されても問題ないが、わかりやすさ重視）
# 電話: 070/080/090-0000-NNNN は実電話番号と被るリスクが低い（0000 は実在しない局番想定）
# 郵便: 999-0000 〜 999-9999（999 局番は実在せず）
_SAFE_PHONE_PREFIX_BY_HASH: tuple[str, ...] = ("070-0000", "080-0000", "090-0000")
_SAFE_POSTAL_PREFIX: str = "999"


def _hash_int(salt: str, surface: str, mod: int) -> int:
    """surface + salt から決定的に [0, mod) の整数を返す."""
    h = hashlib.sha256(f"{salt}:{surface}".encode()).hexdigest()
    return int(h[:8], 16) % mod


def _default_salt() -> str:
    """プロセス毎に安全な乱数 salt を生成 (#145).

    32 bytes (256bit hex = 64 chars) の暗号学的乱数。インスタンス毎に独立した
    salt を持たせることで、ソース固定の salt による fake → surface 辞書攻撃
    での逆引き経路を構造的に塞ぐ。決定性は同一プロセス・同一 strategy 内で
    のみ保証される（永続化したい場合は salt を明示的に渡す）。
    """
    return secrets.token_hex(32)


@dataclass(frozen=True)
class FakerStrategy:
    """Faker (ja_JP) で PII を架空値に置換する戦略 (#128).

    **逆引き耐性なし**: FakerStrategy は LLM オブザーバビリティの可読性向上が
    主目的で、暗号学的な逆引き保護は提供しない。攻撃者が salt と fake を両方
    知っている場合、候補 surface 集合の辞書攻撃で逆引きが可能。
    暗号学的保護が必要な場合は `Hash` 戦略を使い、salt を秘密として扱う。

    Args:
        locale: Faker のロケール。デフォルト `"ja_JP"`。
        salt: 決定性モードで surface → fake のマップに使うソルト。
            **デフォルトはインスタンス毎の `secrets.token_hex(32)` 自動生成** (#145)。
            これによりソース固定の salt による逆引き経路を遮断する。
            永続化（マルチプロセス間で同じ fake を返したい）が必要な場合のみ
            明示的に文字列を渡す（秘密として保護すること）。
        deterministic: True (デフォルト) で同一 surface に同一架空値を返す。
            False では呼び出しごとにランダムな架空値（context preservation 失効）。
        keep_mapping: True で `MaskResult.mapping` に `{fake: 元 surface}` を残す。
            デフォルトは **False**（mapping は空 dict）。Hash 戦略と整合させ、
            「detect, never retain」設計原則を守る (#139)。LLM trace 等に mapping を
            書き出すと PII が漏れるため、明示的に有効化したときのみ保持する。
        max_cache_size: `(entity_type, surface) → fake` の決定性キャッシュの上限 (#177).
            デフォルト **8192** (Hash 戦略の `lru_cache(maxsize=8192)` と同等)。
            上限超過時は最古アクセスのエントリを LRU で破棄する。長時間稼働で
            高カードナリティ surface が流入してもメモリは bounded のまま保たれる。
            `0` を渡すと無制限 (旧挙動)。

    **再検出問題への対応**: Faker が生成する電話番号 / 郵便番号 / CC / マイナンバー /
    法人番号は fuseji の認識器が再度 PII として検出する形式になりうる。再検出を
    避けたい場合:

    - `JP_PHONE_NUMBER` / `JP_POSTAL_CODE`: 安全な fictitious format を使う
      （`070-0000-XXXX` / `999-XXXX`）
    - `MY_NUMBER` / `CREDIT_CARD` / `CORPORATE_NUMBER`: 固定マスク `<MASKED>` で置換
      （番号法対応 + Luhn 通過の架空 CC 生成回避）

    `[faker]` extra でインストール:
    ```bash
    pip install 'fuseji[faker]'
    ```

    Example:
        Faker がインストールされている前提:

        >>> from fuseji import Masker
        >>> from fuseji.faker_strategy import FakerStrategy  # doctest: +SKIP
        >>> strategy = FakerStrategy(salt="example")  # doctest: +SKIP
        >>> masker = Masker(strategy=strategy)  # doctest: +SKIP
        >>> result = masker.mask("田中さん a@b.com")  # doctest: +SKIP
        >>> # 例: '佐藤さん user@example.com' のような架空値に置換される
    """

    locale: str = "ja_JP"
    # salt はインスタンス毎のランダム値をデフォルト (#145)。ソース固定 salt 由来の
    # 逆引き経路を遮断する。永続化が必要なら明示的に文字列を渡す。
    salt: str = field(default_factory=_default_salt)
    deterministic: bool = True
    keep_mapping: bool = False
    # cache を bounded 化 (#177)。Hash 戦略の lru_cache(maxsize=8192) と整合させ、
    # 高カードナリティ surface 流入でメモリが単調増加するのを防ぐ。
    # 0 を指定すると無制限 (旧挙動)。
    max_cache_size: int = 8192
    _faker_cache: OrderedDict[str, str] = field(default_factory=OrderedDict, init=False, repr=False)
    # Faker インスタンスを strategy あたり **スレッド毎** に持つ lazy holder (#142 / #210)。
    # locale プロバイダのロードは数 ms 〜十数 ms かかるため、surface ごとに
    # `Faker(self.locale)` を作り直さず seed_instance で seed のみ差し替える。
    # 旧実装は単一 Faker を全スレッドで共有していたが、複数スレッドが同時に
    # `seed_instance` を呼ぶと race condition で決定性が破綻する (#210)。
    # threading.local で per-thread instance にすることで lock contention 無しに
    # スレッド安全性を確保する。
    _faker_local: threading.local = field(default_factory=threading.local, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            import faker  # noqa: F401
        except ImportError as e:
            msg = (
                "FakerStrategy を使うには Faker が必要です。"
                "`pip install fuseji[faker]` でインストールしてください。"
            )
            raise InvalidConfigError(msg) from e
        if not self.salt:
            raise InvalidConfigError("salt は空文字列にできません")

    def __repr__(self) -> str:
        # salt は repr に露出させない (#145)。ログ漏洩から逆引き経路を遮断。
        return (
            f"FakerStrategy(locale={self.locale!r}, "
            f"salt=<redacted>, "
            f"deterministic={self.deterministic}, "
            f"keep_mapping={self.keep_mapping})"
        )

    def _build_faker(self, surface: str) -> Faker:
        # Faker(self.locale) は数 ms 〜十数 ms かかるため per-thread に 1 回だけ構築 (#142 / #210)。
        # seed_instance は軽量 (provider rebuild なし) だが thread-safe ではないため
        # threading.local で per-thread instance を持つ。lock contention 無し、
        # スレッド数倍の初期化コストはあるが uvicorn worker 数 (数〜数十) で許容範囲。
        fake = getattr(self._faker_local, "fake", None)
        if fake is None:
            from faker import Faker

            fake = Faker(self.locale)
            self._faker_local.fake = fake
        if self.deterministic:
            # 同一 surface → 同一 Faker seed
            seed = int(hashlib.sha256(f"{self.salt}:{surface}".encode()).hexdigest()[:16], 16)
            fake.seed_instance(seed)
        return fake

    def _fake_for(self, entity_type: str, surface: str) -> str:
        """type と surface に応じた架空値を返す（決定的モードはキャッシュ経由）."""
        cache_key = f"{entity_type}:{surface}"
        if self.deterministic and cache_key in self._faker_cache:
            # LRU: ヒットしたエントリを末尾に動かす (#177)
            self._faker_cache.move_to_end(cache_key)
            return self._faker_cache[cache_key]

        if entity_type in _FIXED_MASK_TYPES:
            # 高センシティビティ type は固定マスクで再検出回避
            value = _FIXED_MASK_LABEL
        elif entity_type == PERSON:
            value = self._build_faker(surface).name()
        elif entity_type == EMAIL:
            # Faker の `safe_email` は example.com/example.org/example.net を返すため
            # RFC 6761 reserved domain で再検出問題なし
            value = self._build_faker(surface).safe_email()
        elif entity_type == JP_PHONE_NUMBER:
            # 安全な fictitious format: 070/080/090-0000-XXXX
            prefix_idx = _hash_int(self.salt + "phone", surface, len(_SAFE_PHONE_PREFIX_BY_HASH))
            suffix = _hash_int(self.salt + "phone_suffix", surface, 10000)
            value = f"{_SAFE_PHONE_PREFIX_BY_HASH[prefix_idx]}-{suffix:04d}"
        elif entity_type == JP_POSTAL_CODE:
            # 999 局番は実在しない → 再検出されてもダミー
            suffix = _hash_int(self.salt + "postal", surface, 10000)
            value = f"{_SAFE_POSTAL_PREFIX}-{suffix:04d}"
        else:
            # 未知の type: 固定マスク
            value = f"<{entity_type}>"

        if self.deterministic:
            self._faker_cache[cache_key] = value
            # 上限超過時は最古エントリを LRU で捨てる (#177)。max_cache_size=0 は無制限。
            if self.max_cache_size and len(self._faker_cache) > self.max_cache_size:
                self._faker_cache.popitem(last=False)
        return value

    def mask(self, text: str, entities: Sequence[Entity]) -> tuple[str, Mapping[str, str]]:
        if not entities:
            return text, {}
        replacements: list[tuple[int, int, str]] = []
        mapping: dict[str, str] = {}
        for e in entities:
            fake = self._fake_for(e.type, e.text)
            replacements.append((e.start, e.end, fake))
            # **デフォルトでは mapping を空に保つ** (#139)。Hash 戦略の keep_mapping=False
            # と整合させ「detect, never retain」設計原則を守る。`keep_mapping=True` を
            # 明示指定したときのみ fake → 元 surface を返す（後で復元が必要な用途向け）。
            if self.keep_mapping:
                mapping[fake] = e.text
        return _replace_spans(text, replacements), mapping
