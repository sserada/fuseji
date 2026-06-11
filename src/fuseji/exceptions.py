"""fuseji 例外階層。

利用側で `except FusejiError` だけ書けば fuseji 由来の例外を一括で
キャッチでき、spaCy ロード失敗や FastAPI フレームワーク例外と区別できる。

`InvalidEntityError` と `InvalidConfigError` は `FusejiError` 階層に属しつつ
`ValueError` も継承する多重継承で、既存の `except ValueError` も従来通り
拾える非破壊的設計。
"""

from __future__ import annotations


class FusejiError(Exception):
    """fuseji が発生させる例外の基底クラス。

    `except FusejiError` で fuseji 由来の例外のみをキャッチできる。
    """


class InvalidEntityError(FusejiError, ValueError):
    """Entity の構築時にフィールドが不正な場合の例外。

    既存コードとの互換性のため `ValueError` も多重継承している。
    """


class InvalidConfigError(FusejiError, ValueError):
    """戦略・Vault・Masker 等の設定が不正な場合の例外。

    既存コードとの互換性のため `ValueError` も多重継承している。
    """
