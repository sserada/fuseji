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


@dataclass(frozen=True)
class FakerStrategy:
    """Faker (ja_JP) で PII を架空値に置換する戦略 (#128).

    Args:
        locale: Faker のロケール。デフォルト `"ja_JP"`。
        salt: 決定性モードで surface → fake のマップに使うソルト。
            デフォルトは固定値だがプロセス起動時にランダム化する運用も推奨。
        deterministic: True (デフォルト) で同一 surface に同一架空値を返す。
            False では呼び出しごとにランダムな架空値（context preservation 失効）。
        keep_mapping: True で `MaskResult.mapping` に `{fake: 元 surface}` を残す。
            デフォルトは **False**（mapping は空 dict）。Hash 戦略と整合させ、
            「detect, never retain」設計原則を守る (#139)。LLM trace 等に mapping を
            書き出すと PII が漏れるため、明示的に有効化したときのみ保持する。

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
    salt: str = "fuseji-default-salt-please-override"
    deterministic: bool = True
    keep_mapping: bool = False
    _faker_cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    # Faker インスタンスを strategy あたり 1 個だけ持つ lazy holder (#142)。
    # locale プロバイダのロードは数 ms 〜十数 ms かかるため、surface ごとに
    # `Faker(self.locale)` を作り直さず seed_instance で seed のみ差し替える。
    _faker_holder: list[Faker] = field(default_factory=list, init=False, repr=False)

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

    def _build_faker(self, surface: str) -> Faker:
        # Faker(self.locale) は数 ms 〜十数 ms かかるため strategy 毎に 1 回だけ構築 (#142)。
        # seed_instance は軽量（provider rebuild なし）なので surface ごとに seed のみ差し替える。
        if not self._faker_holder:
            from faker import Faker

            self._faker_holder.append(Faker(self.locale))
        fake = self._faker_holder[0]
        if self.deterministic:
            # 同一 surface → 同一 Faker seed
            seed = int(hashlib.sha256(f"{self.salt}:{surface}".encode()).hexdigest()[:16], 16)
            fake.seed_instance(seed)
        return fake

    def _fake_for(self, entity_type: str, surface: str) -> str:
        """type と surface に応じた架空値を返す（決定的モードはキャッシュ経由）."""
        cache_key = f"{entity_type}:{surface}"
        if self.deterministic and cache_key in self._faker_cache:
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
