"""仮名化バウルト — placeholder ↔ 元テキストの対応をセッション内で保持し復元を可能にする."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable
from typing import Protocol

from . import entity_types

# Placeholder の正規表現。形式は ``<TYPE_N>``（TYPE は大文字スネーク、N は 1 以上の整数）。
# restore で「登録済み placeholder のみ」を狙い撃ちするために使う。
_PLACEHOLDER_PATTERN = re.compile(r"<[A-Z][A-Z_]*_\d+>")


class Vault(Protocol):
    """仮名化バウルトのプロトコル。

    Masker は検出した各エンティティに対し `assign` を呼んで placeholder を取得し、
    LLM への送信前にテキストへ反映する。LLM 応答は `restore` で元テキストに戻せる。
    """

    def assign(self, entity_type: str, surface: str) -> str | None:
        """指定 (type, surface) に placeholder を割り当てて返す。

        除外 type の場合は None を返す（呼び出し側で別途マスクする必要がある）。
        """
        ...

    def get(self, placeholder: str) -> str | None:
        """placeholder から元 surface を取得。未登録なら None。"""
        ...

    def restore(self, text: str) -> str:
        """text 中の登録済み placeholder を元 surface に置換して返す。"""
        ...

    def clear(self) -> None:
        """すべての placeholder マッピングを破棄し、空の状態に戻す。"""
        ...


class InMemoryVault:
    """インメモリ実装の Vault。

    - 同一 (type, surface) には常に同一 placeholder を返す。
    - placeholder 形式は ``<TYPE_N>``（N は type ごとに 1 から付番）。
    - `excluded_types` に含まれる type は `assign` で None を返し、対応表に
      残さない。デフォルトは ``MY_NUMBER``（番号法対応で復元を許さない）。

    Thread-safety:
        `assign` は内部 `threading.Lock` で保護されている。Uvicorn の
        thread pool 経由で並行に呼び出されてもカウンタ採番衝突や同一
        (type, surface) への重複 placeholder 発行は起きない。
        `get` / `restore` は dict 読み取りのみで CPython の GIL に守られる
        ため lock 不要。

    Example:
        >>> from fuseji import InMemoryVault
        >>> vault = InMemoryVault()
        >>> vault.assign("PERSON", "山田")
        '<PERSON_1>'
        >>> vault.assign("PERSON", "山田")  # 同じ surface には同じ placeholder
        '<PERSON_1>'
        >>> vault.assign("MY_NUMBER", "123456789012")  # 除外 type は None
        >>> vault.restore("<PERSON_1>さん")
        '山田さん'
    """

    #: 復元を許さないデフォルトの type 集合。
    #: - ``MY_NUMBER``: 番号法対応で復元禁止
    #: - ``CREDIT_CARD``: PCI DSS Requirement 3.4/3.5 で「保存禁止または強い保護下」が
    #:   求められる PAN を mapping に残さない（#84）
    DEFAULT_EXCLUDED_TYPES: frozenset[str] = frozenset(
        {entity_types.MY_NUMBER, entity_types.CREDIT_CARD}
    )

    def __init__(self, excluded_types: Iterable[str] | None = None) -> None:
        self._excluded: frozenset[str] = (
            frozenset(excluded_types) if excluded_types is not None else self.DEFAULT_EXCLUDED_TYPES
        )
        self._counters: dict[str, int] = {}
        self._surface_to_placeholder: dict[tuple[str, str], str] = {}
        self._placeholder_to_surface: dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def excluded_types(self) -> frozenset[str]:
        return self._excluded

    @property
    def size(self) -> int:
        """登録済み placeholder の総数。

        モニタリング・長時間稼働サーバーでのメモリ使用量推定・テストで
        clear() の効果を確認する用途に使う。excluded type 由来の固定
        `<TYPE>` placeholder（assign が None を返したもの）はカウントされない。
        """
        return len(self._placeholder_to_surface)

    def __repr__(self) -> str:
        excluded = sorted(self._excluded)
        return f"InMemoryVault(size={self.size}, excluded_types={excluded!r})"

    def assign(self, entity_type: str, surface: str) -> str | None:
        if entity_type in self._excluded:
            return None
        key = (entity_type, surface)
        # Lock の外で先読みする fast-path で、既存 placeholder のときは
        # ロック取得を回避できる（dict.get は atomic）。
        cached = self._surface_to_placeholder.get(key)
        if cached is not None:
            return cached
        # 新規割当は競合を避けるためロック内で再チェック → 採番。
        with self._lock:
            cached = self._surface_to_placeholder.get(key)
            if cached is not None:
                return cached
            self._counters[entity_type] = self._counters.get(entity_type, 0) + 1
            placeholder = f"<{entity_type}_{self._counters[entity_type]}>"
            self._surface_to_placeholder[key] = placeholder
            self._placeholder_to_surface[placeholder] = surface
            return placeholder

    def get(self, placeholder: str) -> str | None:
        return self._placeholder_to_surface.get(placeholder)

    def restore(self, text: str) -> str:
        """text 中の登録済み placeholder を元 surface に置換して返す。

        ``<TYPE_N>`` 形式に一致するトークンのみを対象とし、その中で vault に
        登録されているものだけを置換する。未登録 placeholder（別 vault 由来、
        excluded type の番号なし ``<TYPE>``、偶然テキストに含まれた文字列等）は
        素通しする。これにより:

        - 二重マスクや別セッションの placeholder が混入しても誤復元しない
        - ``<PERSON_1>`` が ``<PERSON_11>`` の部分一致になる誤置換を構造的に防ぐ
        - 1 パスの O(n) 置換になり、登録数 m に対して O(m·n) → O(n) に改善
        """
        return _PLACEHOLDER_PATTERN.sub(
            lambda m: self._placeholder_to_surface.get(m.group(), m.group()),
            text,
        )

    def clear(self) -> None:
        """すべての placeholder マッピングと番号カウンタを破棄して空の状態に戻す。

        セッション境界の明示的なリセット、長時間稼働サーバーでの定期的な
        メモリ解放、テスト間でインスタンスを使い回す場合などに使う。

        `excluded_types` の設定は維持される（再構築不要）。

        Thread-safety: `assign` と同じ Lock で保護されているため並行呼び出し
        中に部分的な状態が観測されることはない。

        Example:
            >>> from fuseji import InMemoryVault
            >>> v = InMemoryVault()
            >>> v.assign("PERSON", "山田")
            '<PERSON_1>'
            >>> v.clear()
            >>> v.get("<PERSON_1>")  # クリア後は未登録扱い
            >>> v.assign("PERSON", "佐藤")  # カウンタも 1 から再開
            '<PERSON_1>'
        """
        with self._lock:
            self._counters.clear()
            self._surface_to_placeholder.clear()
            self._placeholder_to_surface.clear()
