"""旧 example のインポートパス互換用 (#129 → #161).

v0.3 開発中の途中で `fuseji.integrations.otel` として公式モジュール化された (#161)。
本ファイルは旧 example の `from mask_processor import ...` 経路を壊さないため
の薄い再エクスポート。新規実装は `from fuseji.integrations.otel import ...` を
使うこと。
"""

from __future__ import annotations

from fuseji.integrations.otel import (
    DEFAULT_ATTRIBUTE_KEYS,
    mask_attribute,
    mask_attributes,
)

__all__ = [
    "DEFAULT_ATTRIBUTE_KEYS",
    "mask_attribute",
    "mask_attributes",
]
