"""仮名化バウルト — placeholder ↔ 元テキストの対応をセッション内で保持し復元を可能にする."""

from __future__ import annotations

import re
import secrets
import threading
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from typing import Protocol

from . import entity_types
from .exceptions import InvalidConfigError

# Placeholder の基本形式。実際は `<TYPE_N_nonce>` で末尾にインスタンス固有の
# 16 進 nonce が付く（#81、クロステナント衝突対策）。下の正規表現は型と数値の
# パターンを抑えるためだけのリファレンスで、復元用パターンは Vault インスタンス
# ごとに `_placeholder_pattern` として動的にコンパイルする。
_PLACEHOLDER_PREFIX_PATTERN = r"<[A-Z][A-Z_]*_\d+"


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

    def assign_many(self, pairs: Sequence[tuple[str, str]]) -> list[str | None]:
        """複数の (type, surface) ペアに対し一括で placeholder を割り当てる。

        `assign` を要素数だけ呼ぶのと意味的に等価だが、実装は 1 回の lock 取得で
        全件を処理できる（`VaultStrategy.mask` で k 回の lock contention を 1 回に
        削減するための最適化）。

        デフォルト実装は individual `assign` を順に呼ぶ。並列性能を求める実装は
        オーバーライドする（`InMemoryVault.assign_many` は単一 lock 内で処理）。

        Args:
            pairs: `(entity_type, surface)` のシーケンス。

        Returns:
            `pairs` と同じ長さの placeholder（または None）のリスト。
        """
        return [self.assign(t, s) for t, s in pairs]

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
      残さない。デフォルトは ``{MY_NUMBER, CREDIT_CARD}``。
    - `max_size` を指定すると、登録済み placeholder 数の上限を設ける。
      上限到達後の新規 `assign` では FIFO で最古エントリを退避（#86）。
      長時間稼働サーバーでメモリ使用量とメモリダンプ経由の事後流出リスクを
      抑止する DoS 緩和策。

    Thread-safety:
        `assign` は内部 `threading.Lock` で保護されている。Uvicorn の
        thread pool 経由で並行に呼び出されてもカウンタ採番衝突や同一
        (type, surface) への重複 placeholder 発行は起きない。
        `get` / `restore` は dict 読み取りのみで CPython の GIL に守られる
        ため lock 不要。

    Example:
        Placeholder の末尾には Vault インスタンス固有 nonce が付く (#81)。
        テスト・docstring の再現性を確保するため、明示的に `nonce` を指定する:

        >>> from fuseji import InMemoryVault
        >>> vault = InMemoryVault(nonce="test")
        >>> vault.assign("PERSON", "山田")
        '<PERSON_1_test>'
        >>> vault.assign("PERSON", "山田")  # 同じ surface には同じ placeholder
        '<PERSON_1_test>'
        >>> vault.assign("MY_NUMBER", "123456789012")  # 除外 type は None
        >>> vault.restore("<PERSON_1_test>さん")
        '山田さん'

        通常運用では `nonce` を省略し、`secrets.token_hex(4)` で自動生成された
        値を使う（クロス Vault 衝突を構造的に防ぐ）。
    """

    #: 復元を許さないデフォルトの type 集合。
    #: - ``MY_NUMBER``: 番号法対応で復元禁止
    #: - ``CREDIT_CARD``: PCI DSS Requirement 3.4/3.5 で「保存禁止または強い保護下」が
    #:   求められる PAN を mapping に残さない（#84）
    DEFAULT_EXCLUDED_TYPES: frozenset[str] = frozenset(
        {entity_types.MY_NUMBER, entity_types.CREDIT_CARD}
    )

    def __init__(
        self,
        excluded_types: Iterable[str] | None = None,
        *,
        max_size: int | None = None,
        nonce: str | None = None,
    ) -> None:
        if max_size is not None and max_size < 1:
            raise InvalidConfigError(f"max_size は 1 以上の整数: {max_size}")
        self._excluded: frozenset[str] = (
            frozenset(excluded_types) if excluded_types is not None else self.DEFAULT_EXCLUDED_TYPES
        )
        self._max_size = max_size
        # nonce: インスタンス固有のランダム文字列。クロステナント衝突対策 (#81)。
        # 別 Vault が生成した `<EMAIL_1>` 形式の文字列がたまたま自分のテキストに
        # 含まれても、nonce が一致しないため `restore` で誤復元しない。
        # `nonce=...` を明示指定するとテスト等での再現性が確保できる。
        if nonce is None:
            self._nonce = secrets.token_hex(4)  # 8 hex chars, 32 bits
        else:
            if not re.fullmatch(r"[A-Za-z0-9]+", nonce):
                raise InvalidConfigError(f"nonce は英数字のみ: {nonce!r}")
            self._nonce = nonce
        # 復元用正規表現も nonce を含む形でインスタンスごとにコンパイル。
        # これにより別 Vault 由来の placeholder は構造的にマッチしない。
        self._placeholder_pattern = re.compile(
            _PLACEHOLDER_PREFIX_PATTERN + r"_" + re.escape(self._nonce) + r">"
        )
        self._counters: dict[str, int] = {}
        # OrderedDict で挿入順を保持し、`max_size` 到達時に FIFO で退避できるようにする。
        # 両辞書は assign 内で常に同時に更新されるので、挿入順が一致する前提。
        self._surface_to_placeholder: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._placeholder_to_surface: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def excluded_types(self) -> frozenset[str]:
        return self._excluded

    @property
    def nonce(self) -> str:
        """インスタンス固有 placeholder nonce (#81)。

        `<TYPE_N_nonce>` 形式の placeholder の末尾に付く。テスト・デバッグ・
        外部システムとの placeholder 書式の合わせ込み目的でのみ参照する。
        """
        return self._nonce

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
            return self._assign_locked(entity_type, surface)

    def assign_many(self, pairs: Sequence[tuple[str, str]]) -> list[str | None]:
        """複数 (type, surface) ペアを 1 回の lock 取得で一括採番する (#97)。

        VaultStrategy が新規 PII 群を投入する経路で k 回の lock contention を
        1 回に削減できる。並行リクエスト下での `assign` 直列化を抑止する。
        """
        if not pairs:
            return []
        results: list[str | None] = [None] * len(pairs)
        # excluded type は lock 不要で None を返せる。残りを lock 内で処理。
        pending: list[tuple[int, str, str]] = []
        for i, (etype, surface) in enumerate(pairs):
            if etype in self._excluded:
                results[i] = None
                continue
            # fast-path: 既存 placeholder は lock 取らずに返す
            cached = self._surface_to_placeholder.get((etype, surface))
            if cached is not None:
                results[i] = cached
            else:
                pending.append((i, etype, surface))
        if pending:
            with self._lock:
                for i, etype, surface in pending:
                    results[i] = self._assign_locked(etype, surface)
        return results

    def _assign_locked(self, entity_type: str, surface: str) -> str:
        """lock 取得済みの状態で 1 件採番する内部実装。

        Caller は `self._lock` を保持していること。`entity_type` が
        `_excluded` でないこと、cache miss が確認済みであることが前提だが、
        並行性のため再 check してから採番する（double-checked locking）。
        """
        key = (entity_type, surface)
        cached = self._surface_to_placeholder.get(key)
        if cached is not None:
            return cached
        self._counters[entity_type] = self._counters.get(entity_type, 0) + 1
        # `<TYPE_N_nonce>` 形式。nonce はインスタンス固有 (#81)。
        placeholder = f"<{entity_type}_{self._counters[entity_type]}_{self._nonce}>"
        self._surface_to_placeholder[key] = placeholder
        self._placeholder_to_surface[placeholder] = surface
        # max_size 超過時は FIFO で最古エントリを退避（counters は維持して
        # 新規 placeholder 番号の単調増加を保つ — 退避済み番号は再利用しない）
        if self._max_size is not None:
            while len(self._placeholder_to_surface) > self._max_size:
                self._surface_to_placeholder.popitem(last=False)
                self._placeholder_to_surface.popitem(last=False)
        return placeholder

    def get(self, placeholder: str) -> str | None:
        return self._placeholder_to_surface.get(placeholder)

    def restore(self, text: str) -> str:
        """text 中の登録済み placeholder を元 surface に置換して返す。

        ``<TYPE_N_nonce>`` 形式のうち、本 Vault インスタンスの nonce に
        一致するもののみを対象とし、その中で vault に登録されているものだけを
        置換する。未登録 placeholder や別 Vault 由来（nonce 不一致）は構造的に
        素通しする。これにより:

        - 二重マスクや別 Vault の placeholder が混入しても誤復元しない (#81)
        - 攻撃者が ``<EMAIL_1_xxxx>`` を推測しても nonce が一致しないと無効
        - ``<PERSON_1_x>`` が ``<PERSON_11_x>`` の部分一致になる誤置換を構造的に防ぐ
        - 1 パスの O(n) 置換になり、登録数 m に対して O(m·n) → O(n) に改善
        """
        return self._placeholder_pattern.sub(
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
            >>> v = InMemoryVault(nonce="test")
            >>> v.assign("PERSON", "山田")
            '<PERSON_1_test>'
            >>> v.clear()
            >>> v.get("<PERSON_1_test>")  # クリア後は未登録扱い
            >>> v.assign("PERSON", "佐藤")  # カウンタも 1 から再開
            '<PERSON_1_test>'
        """
        with self._lock:
            self._counters.clear()
            self._surface_to_placeholder.clear()
            self._placeholder_to_surface.clear()
