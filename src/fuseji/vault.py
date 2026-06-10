"""仮名化バウルト — placeholder ↔ 元テキストの対応をセッション内で保持し復元を可能にする."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


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


class InMemoryVault:
    """インメモリ実装の Vault。

    - 同一 (type, surface) には常に同一 placeholder を返す。
    - placeholder 形式は ``<TYPE_N>``（N は type ごとに 1 から付番）。
    - `excluded_types` に含まれる type は `assign` で None を返し、対応表に
      残さない。デフォルトは ``MY_NUMBER``（番号法対応で復元を許さない）。
    """

    #: 復元を許さないデフォルトの type 集合（番号法対応）
    DEFAULT_EXCLUDED_TYPES: frozenset[str] = frozenset({"MY_NUMBER"})

    def __init__(self, excluded_types: Iterable[str] | None = None) -> None:
        self._excluded: frozenset[str] = (
            frozenset(excluded_types) if excluded_types is not None else self.DEFAULT_EXCLUDED_TYPES
        )
        self._counters: dict[str, int] = {}
        self._surface_to_placeholder: dict[tuple[str, str], str] = {}
        self._placeholder_to_surface: dict[str, str] = {}

    @property
    def excluded_types(self) -> frozenset[str]:
        return self._excluded

    def assign(self, entity_type: str, surface: str) -> str | None:
        if entity_type in self._excluded:
            return None
        key = (entity_type, surface)
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
        # 長い placeholder から処理して部分一致による誤置換を防ぐ
        result = text
        for placeholder, surface in sorted(
            self._placeholder_to_surface.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            result = result.replace(placeholder, surface)
        return result
