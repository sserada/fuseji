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
| `max_json_depth` | `100` | `mask_json` の再帰深度上限。N 段までネスト許容、N 段目で fail-closed |
| `mask_dict_keys` | `False` | `True` で `mask_json` が dict のキー（str のみ）も値と同じ戦略でマスク |

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
    length: int = 16          # 1-64 の範囲、デフォルト 16 (64bit)
    keep_mapping: bool = False  # True で {hash: 元 surface} を返す（デフォルトは空）
```

SHA256 ハッシュ hex の先頭 N 文字で置換。同一表層形は同一ハッシュ。

**セキュリティ（v0.2 以降）**:
- デフォルト `length=16` でレインボー攻撃耐性を強化（v0.1 は 8）
- `mapping` はデフォルトで空 dict。`keep_mapping=True` を明示指定したときのみ `{hash: 元 surface}` を返す
- 戻り値 `mapping` を経由した PII 漏洩経路を遮断する

> ⚠️ `Hash` という名前は Python ビルトインの `hash()` 関数と紛らわしいことがあります。混在環境では `from fuseji import Hash as HashStrategy` のエイリアス import を検討してください。

---

## Vault

### `Vault`

`fuseji.vault.Vault` — 仮名化バウルトのプロトコル。

```python
class Vault(Protocol):
    def assign(self, entity_type: str, surface: str) -> str | None: ...
    def assign_many(
        self, pairs: Sequence[tuple[str, str]]
    ) -> list[str | None]: ...
    def get(self, placeholder: str) -> str | None: ...
    def restore(self, text: str) -> str: ...
    def clear(self) -> None: ...
```

- **`assign(type, surface)`** — `(type, surface)` に placeholder を割り当てて返す。excluded type の場合は `None`（呼び出し側で別途マスクする必要あり）
- **`assign_many(pairs)`** — `(type, surface)` のシーケンスを一括採番。`InMemoryVault` 実装では 1 回の lock 取得で全件処理し、並列リクエスト下での contention を軽減（#97）。default 実装は `assign` の繰り返し
- **`get(placeholder)`** — placeholder から元 surface を取得。未登録なら `None`
- **`restore(text)`** — text 中の登録済み placeholder を元 surface に置換して返す
- **`clear()`** — すべての placeholder マッピングを破棄して空の状態に戻す

### `InMemoryVault`

```python
class InMemoryVault:
    DEFAULT_EXCLUDED_TYPES: frozenset[str] = frozenset({"MY_NUMBER", "CREDIT_CARD"})

    def __init__(
        self,
        excluded_types: Iterable[str] | None = None,
        *,
        max_size: int | None = None,
    ) -> None: ...

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
- デフォルトは `{"MY_NUMBER", "CREDIT_CARD"}`:
  - `MY_NUMBER` は番号法対応で復元を許さない
  - `CREDIT_CARD` は PCI DSS Requirement 3.4/3.5 整合で PAN を mapping に残さない
- `excluded_types` を空指定で除外集合自体を無効化することは可能（法令／コンプライアンス上の責任は利用者側に帰属）
- `max_size` を指定すると登録済み placeholder 数の上限を設け、超過時は FIFO で最古エントリを退避する。長時間稼働サーバーでのメモリ無制限成長を抑止する DoS 緩和策（#86）。`max_size=None`（デフォルト）は無制限
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
    entity_type: str  # 種別名（例: "EMAIL"）
    name: str         # 認識器の識別子（snake_case）。`Entity.recognizer` に格納
    def analyze(
        self, text: str, *, normalized: str | None = None
    ) -> Iterable[Entity]: ...
```

`normalized` には `Masker.detect` が 1 回だけ計算した `normalize(text)`（全角→半角の
数字・ハイフン正規化）が渡される。正規化を必要としない認識器（例: EMAIL）はこの
引数を無視してよいが、シグネチャ上は必ず受け取る必要がある（v0.2 で破壊的変更）。

### `regex_analyze`

`fuseji.recognizers.base.regex_analyze` — regex ベース認識器の共通テンプレート関数。
正規表現マッチに加えて、文字正規化・桁境界判定・セパレーター除去・検証関数の
適用を一括で提供する。

```python
def regex_analyze(
    text: str,
    *,
    entity_type: str,
    recognizer_name: str,
    pattern: re.Pattern[str],
    default_score: float = 1.0,
    validate: Callable[[str], float | None] | None = None,
    normalize_fn: Callable[[str], str] | None = None,
    normalized: str | None = None,
    require_digit_boundary: bool = False,
    strip_separators_before_validate: bool = False,
) -> Iterator[Entity]: ...
```

- `validate` が `None` でなく返り値が `None` の場合、その候補は除外
- `normalize_fn` は 1 文字 ↔ 1 文字の変換のみ許容（オフセット維持のため）
- `normalized` は Masker 層で事前計算した正規化済みテキストを渡すための引数。
  指定時は `normalize_fn` を呼ばずにこの値を使う（同じ計算の重複を避ける最適化）
- `Entity.text` は元テキストの表層形（正規化後ではない）

カスタム認識器の追加例は [CONTRIBUTING.md](../CONTRIBUTING.md) を参照。

### 事前正規化の最適化 (#24)

`Masker.detect` は、登録された認識器のうち少なくとも 1 つが `analyze` メソッドに
`normalized` キーワード引数を受け取れる場合、`normalize(text)` を 1 回だけ計算し
全ての対応認識器に渡す。これにより、複数の正規表現ベース認識器が同じ正規化処理を
独立に走らせていた状況が解消される。

カスタム認識器がこの最適化に乗るには、`analyze(self, text, *, normalized=None)`
のシグネチャを採用する。受け取らない（旧シグネチャ）認識器は従来どおり動作する。

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

`fuseji.server.app`（`[server]` extra 必須）

### エンドポイント

- `POST /mask` — 任意 JSON を `Masker.mask_json` で再帰マスク
- `POST /detect` — テキストから entity 一覧を返す
- `GET /healthz` — `{"status": "ok"}` を返す
- `GET /openapi.json` — OpenAPI 自動生成スキーマ

```bash
pip install 'fuseji[server]'
uvicorn fuseji.server.app:app --host 0.0.0.0 --port 8000
```

### `create_app(...)` factory

カスタム `Masker` / リソース上限を指定するための DI factory。

```python
def create_app(
    masker: Masker | None = None,
    *,
    max_body_bytes: int | None = None,
    timeout_seconds: float | None = None,
    api_key: str | None = None,
    cors_origins: Sequence[str] | None = None,
) -> FastAPI: ...
```

| 引数 | デフォルト | 説明 |
| --- | --- | --- |
| `masker` | `Masker()`（v0.1 デフォルト認識器） | カスタム認識器・Vault・NER を統合したい場合に明示指定 |
| `max_body_bytes` | `FUSEJI_SERVER_MAX_BODY_BYTES` or 1 MB | `Content-Length` が超過すると HTTP 413 |
| `timeout_seconds` | `FUSEJI_SERVER_TIMEOUT_SECONDS` or 30 秒 | 1 リクエスト処理が超過すると HTTP 504 |
| `api_key` | `FUSEJI_API_KEY` or `None` (無認証) | `X-API-Key` ヘッダで認証。`/healthz` `/openapi.json` は保護対象外 |
| `cors_origins` | `FUSEJI_CORS_ORIGINS`（カンマ区切り）or `None` (CORS 無効) | CORS 許可オリジン。インターネット公開時は明示必須 |

```python
from fuseji import Masker, InMemoryVault
from fuseji.server.app import create_app

app = create_app(
    masker=Masker(vault=InMemoryVault()),
    max_body_bytes=512_000,
    timeout_seconds=10.0,
)
```

### ミドルウェア

- `BodySizeLimitMiddleware` — pure ASGI middleware で body stream を逐次読み取り、`Content-Length` 有無に関わらず累積バイト数で 413 判定（chunked 攻撃対応、#87）
- `ApiKeyAuthMiddleware` — `X-API-Key` ヘッダの timing-safe 比較で `/mask` `/detect` を保護（#83、opt-in）
- `RequestTimeoutMiddleware` — `asyncio.wait_for` ベースのレスポンス時間有界化。
  同期エンドポイントが threadpool で実行されるため、タイムアウト発火後もスレッド側の
  処理は継続する（CPU 解放保証はない）。レスポンス時間の有界化が目的の DoS 緩和策。
- `CORSMiddleware`（starlette 標準）— `cors_origins` 指定時のみ登録。`allow_methods=["GET","POST"]`, `allow_headers=["Content-Type","X-API-Key"]`

モジュールスコープ `app = create_app()` は環境変数ベースの既定設定で構築されたインスタンス。
`uvicorn fuseji.server.app:app` で起動するシナリオの後方互換のため残されている。

詳細は [README.md](../README.md) の「サーバーモード」を参照。
