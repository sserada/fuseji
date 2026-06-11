# API リファレンス

公開シンボルは `fuseji` パッケージから直接 import できます。

```python
from fuseji import (
    Masker, Entity, MaskResult,
    Placeholder, Redact, Hash, MaskStrategy,
    Vault, InMemoryVault,
)
```

`__version__` 属性でバージョンを参照できます: `fuseji.__version__`。

---

## `Masker`

`fuseji.engine.Masker` — 認識器・NER バックエンド・戦略・Vault を統合する中核クラス。

```python
class Masker:
    def __init__(
        self,
        recognizers: Sequence[Recognizer] | None = None,
        ner: NerBackend | None = None,
        strategy: MaskStrategy | None = None,
        threshold: float = 0.4,
        vault: Vault | None = None,
    ) -> None: ...

    def detect(self, text: str) -> tuple[Entity, ...]: ...
    def mask(self, text: str) -> MaskResult: ...
    def mask_json(self, data: Any) -> Any: ...
```

### コンストラクタ引数

| 引数 | デフォルト | 説明 |
| --- | --- | --- |
| `recognizers` | `default_recognizers()` | 使用する認識器の列 |
| `ner` | `None` | NER バックエンド（例: `GinzaBackend()`）。`None` で NER 無効 |
| `strategy` | `Placeholder()` | マスキング戦略 |
| `threshold` | `0.4` | このスコア未満は除外（recall 寄り） |
| `vault` | `None` | 仮名化バウルト。指定時は Placeholder 形式で必ずマスクし、戦略指定は無視 |

### メソッド

- **`detect(text)`** — 認識器と NER を走査し、threshold で絞り込み後、オーバーラップをスコア優先で解決した `tuple[Entity, ...]` を返す
- **`mask(text)`** — 検出して戦略でマスクし、`MaskResult` を返す
- **`mask_json(data)`** — `str` / `dict` / `list` / `tuple` を再帰的にマスク。dict キーは PII を含まない前提で値のみマスク。`int` / `float` / `bool` / `None` は素通し

---

## `Entity`

`fuseji.types.Entity` — 検出された PII の表現。

```python
@dataclass(frozen=True, slots=True)
class Entity:
    type: str        # "EMAIL", "JP_PHONE_NUMBER" など
    text: str        # マッチ表層形
    start: int       # 元テキストへのコードポイント開始オフセット（包含）
    end: int         # 元テキストへのコードポイント終端オフセット（除外）
    score: float     # 0.0–1.0
    recognizer: str  # 発火した認識器名
```

`__post_init__` で次を検証:
- `start >= 0`
- `end >= start`
- `0.0 <= score <= 1.0`

---

## `MaskResult`

`fuseji.types.MaskResult` — マスキング処理の結果。

```python
@dataclass(frozen=True, slots=True)
class MaskResult:
    text: str
    entities: tuple[Entity, ...]
    mapping: Mapping[str, str] = field(default_factory=dict)
```

`mapping` は Vault または `Placeholder` / `Hash` 戦略が出力した placeholder → 元 surface の対応表（戦略により意味が異なる: `Placeholder` は placeholder→original、`Hash` は hash→original、`Redact` は空）。

---

## マスキング戦略

### `MaskStrategy`

`fuseji.strategies.MaskStrategy` — 戦略プロトコル。

```python
class MaskStrategy(Protocol):
    def mask(
        self, text: str, entities: Sequence[Entity]
    ) -> tuple[str, Mapping[str, str]]: ...
```

`entities` は `text` 内でオーバーラップしない前提（Masker のオーバーラップ解決後に呼ばれる）。戻り値はマスク済みテキストと対応表のタプル。

### `Placeholder`

```python
@dataclass(frozen=True, slots=True)
class Placeholder: ...
```

`<TYPE_N>` 形式で置換。同一 `(type, surface)` には同一番号、`type` ごとに独立した番号系列、元テキスト出現順で付番。

### `Redact`

```python
@dataclass(frozen=True, slots=True)
class Redact:
    replacement: str = "[REDACTED]"
```

固定文字列で置換。`mapping` は空。

### `Hash`

```python
@dataclass(frozen=True, slots=True)
class Hash:
    length: int = 8  # 1-64 の範囲
```

SHA256 ハッシュ hex の先頭 N 文字で置換。同一表層形は同一ハッシュ。`mapping` には `hash → 元 surface` を保持（既知集合からの逆引きは可能）。

> ⚠️ `Hash` という名前は Python ビルトインの `hash()` 関数と紛らわしいことがあります。混在環境では `from fuseji import Hash as HashStrategy` のエイリアス import を検討してください。

---

## Vault

### `Vault`

`fuseji.vault.Vault` — 仮名化バウルトのプロトコル。

```python
class Vault(Protocol):
    def assign(self, entity_type: str, surface: str) -> str | None: ...
    def get(self, placeholder: str) -> str | None: ...
    def restore(self, text: str) -> str: ...
    def clear(self) -> None: ...
```

- **`assign(type, surface)`** — `(type, surface)` に placeholder を割り当てて返す。excluded type の場合は `None`（呼び出し側で別途マスクする必要あり）
- **`get(placeholder)`** — placeholder から元 surface を取得。未登録なら `None`
- **`restore(text)`** — text 中の登録済み placeholder を元 surface に置換して返す
- **`clear()`** — すべての placeholder マッピングを破棄して空の状態に戻す

### `InMemoryVault`

```python
class InMemoryVault:
    DEFAULT_EXCLUDED_TYPES: frozenset[str] = frozenset({"MY_NUMBER"})

    def __init__(self, excluded_types: Iterable[str] | None = None) -> None: ...

    @property
    def excluded_types(self) -> frozenset[str]: ...

    @property
    def size(self) -> int: ...  # 登録済み placeholder 数

    def clear(self) -> None: ...  # マッピングを破棄。excluded_types 設定は維持

    def __repr__(self) -> str: ...  # InMemoryVault(size=..., excluded_types=...)
```

- 同一 `(type, surface)` には常に同一 placeholder を返す
- placeholder 形式は `<TYPE_N>`（type ごとに 1 から付番）
- `excluded_types` に含まれる type は `assign` で `None` を返し対応表に残さない
- デフォルトは `MY_NUMBER`（番号法対応で復元を許さない）
- `excluded_types` を空指定で `MY_NUMBER` も対応表に含めることは可能（番号法上の責任は利用者側に帰属）
- `assign` は内部 `threading.Lock` で保護されており、Uvicorn の thread pool 経由で並行に呼ばれても安全

---

## エンティティ種別の定数

`fuseji.entity_types` — ハードコード文字列の代わりに使えるタイプセーフな定数モジュール。

```python
from fuseji import entity_types
from fuseji.entity_types import MY_NUMBER, EMAIL  # 直接 import も可

entity_types.EMAIL              # "EMAIL"
entity_types.CREDIT_CARD        # "CREDIT_CARD"
entity_types.MY_NUMBER          # "MY_NUMBER"
entity_types.JP_PHONE_NUMBER    # "JP_PHONE_NUMBER"
entity_types.JP_POSTAL_CODE     # "JP_POSTAL_CODE"
entity_types.PERSON             # "PERSON"
entity_types.V0_1_TYPES         # frozenset of all 6
```

値は `str` そのものなので `Entity.type` 比較や `excluded_types` 渡しに直接使えます。

---

## 例外階層

```python
from fuseji import FusejiError, InvalidEntityError, InvalidConfigError

try:
    masker.mask(...)
except FusejiError:
    # fuseji 由来のみキャッチ
    pass
```

- `FusejiError(Exception)`: fuseji 例外の基底
- `InvalidEntityError(FusejiError, ValueError)`: Entity 構築不正
- `InvalidConfigError(FusejiError, ValueError)`: 戦略・Vault 等の設定不正

`ValueError` も多重継承しているため、既存の `except ValueError` も従来通り動作します。

---

## 認識器

### `Recognizer`

`fuseji.recognizers.base.Recognizer` — 認識器プロトコル。

```python
class Recognizer(Protocol):
    entity_type: str
    def analyze(self, text: str) -> Iterable[Entity]: ...
```

### `default_recognizers()`

```python
def default_recognizers() -> tuple[Recognizer, ...]:
    # EMAIL / CREDIT_CARD / MY_NUMBER / JP_PHONE_NUMBER / JP_POSTAL_CODE の 5 認識器
```

### 正規化ユーティリティ

```python
from fuseji.recognizers import normalize, normalize_digits, normalize_hyphens

normalize_digits("０９０")    # "090"
normalize_hyphens("090ー1234")  # "090-1234"
normalize("０９０ー１２３４")    # "090-1234"
```

すべて 1 文字 ↔ 1 文字。コードポイント長を変えないため、正規化後オフセットは元テキストに対して維持されます。

### ビルトイン認識器

- `EmailRecognizer`（`entity_type="EMAIL"`、score=1.0）
- `CreditCardRecognizer`（`entity_type="CREDIT_CARD"`、score=0.95、Luhn 検証）
- `MyNumberRecognizer`（`entity_type="MY_NUMBER"`、score=0.95/0.5、チェックディジット、recall 優先）
- `JpPhoneRecognizer`（`entity_type="JP_PHONE_NUMBER"`、numbering plan）
- `JpPostalRecognizer`（`entity_type="JP_POSTAL_CODE"`、〒 と文脈ブースト）

---

## NER バックエンド

### `NerBackend`

`fuseji.ner.base.NerBackend` — NER プロトコル。

```python
class NerBackend(Protocol):
    def analyze(self, text: str) -> Iterable[Entity]: ...
```

### `GinzaBackend`

`fuseji.ner.ginza.GinzaBackend`（`[ginza]` extra 必須）

```python
class GinzaBackend:
    def __init__(
        self,
        labels: Iterable[str] | None = None,  # デフォルト ("Person",)
        model_name: str = "ja_ginza",
        score: float = 0.85,
    ) -> None: ...
```

GiNZA の "Person" を慣用名 "PERSON" にマップ、それ以外のラベルは大文字化してそのまま出力。GiNZA 5.2 系の `compound_splitter` は新版 spaCy で設定不整合を起こすため `exclude` でロード。

---

## 連携アダプタ

### `fuseji.integrations.langfuse.make_mask_fn`

```python
def make_mask_fn(masker: Masker | None = None) -> Callable[[Any], Any]: ...
```

Langfuse SDK の `mask` パラメータに渡せる callable を返す。例外時は fail-closed で `"[fuseji: masking failed]"` を返却。

```python
from langfuse import Langfuse
from fuseji.integrations.langfuse import make_mask_fn

langfuse = Langfuse(mask=make_mask_fn())
```

---

## FastAPI サーバー

`fuseji.server.app.app`（`[server]` extra 必須）

エンドポイント:
- `POST /mask` — 任意 JSON を `Masker.mask_json` で再帰マスク
- `POST /detect` — テキストから entity 一覧を返す
- `GET /healthz` — `{"status": "ok"}` を返す
- `GET /openapi.json` — OpenAPI 自動生成スキーマ

```bash
pip install 'fuseji[server]'
uvicorn fuseji.server.app:app --host 0.0.0.0 --port 8000
```

詳細は [README.md](../README.md) の「サーバーモード」を参照。
