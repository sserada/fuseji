# fuseji — 設計ドキュメント (v0.1)

> **fuseji**（伏せ字）— 日本語特化の PII 検出・マスキングミドルウェア（LLM オブザーバビリティパイプライン向け）。

**ステータス**: v0.1 リリース
**ライセンス**: Apache-2.0
**言語**: Python 3.10+（`uv` 管理）

---

## 1. 問題設定

LLM オブザーバビリティ基盤（Langfuse、LangSmith、Phoenix、OTel ベースのスタック）は、機密データをアプリケーション境界外に送る前にマスクするための _hooks_ を提供しています。しかし、これらのフックの参照実装はすべて英語圏向けです（米国の電話番号、SSN、ラテン文字の人名向け正規表現）。

日本語テキストでは既存の検出エコシステムが構造的に失敗します:

- **Presidio** には Japan 対応の認識器がない。マイナンバー、日本の電話番号フォーマット、郵便番号はカバーされず、日本の携帯番号は他ロケールのパターンと偶然一致するだけ
- **LLM Guard** の Anonymize スキャナは英語 BERT NER モデル前提
- **GLiNER PII** モデルは欧州 6 言語をカバーするが、日本語は含まれない
- **OTel Collector** の redaction/transform processor は正規表現専用で、自然文中の人名・住所を扱えない

日本語特有の失敗モードは広く知られています: 単語境界の空白がない（人名検出が崩壊）、大→小の住所順、全角/半角の数字・ハイフンのバリエーション、人名と一般名詞の曖昧性（例「田中工業の田中」）、SSN 風認識器ではマイナンバーが見えない、など。

**fuseji はこの空白を埋めます: 日本語テキスト向けに作られた検出エンジンを、観測ツールが既に公開しているマスキングフックへの drop-in アダプタとして提供します。**

## 2. 設計目標

1. **Japanese-first、Japanese-only ではない。** コア認識器は日本語エンティティを対象としつつ、ASCII エンティティ（email, credit card）は素のままで動作。英語 NER は v0.x の範囲外
2. **エンジンをフックへ持ち込む。** 新たなインフラ概念はゼロ。fuseji は (a) Langfuse SDK の `mask` パラメータ、(b) Langfuse self-hosted の ingestion masking callback、(c) HTTP サイドカーとしての任意 OTel Collector、にプラグイン可能
3. **Recall でフェイルクローズ。** この領域では偽陰性（PII 漏洩）のコストが偽陽性（過剰マスク）よりはるかに高い。デフォルトしきい値は recall 寄り
4. **予測可能なレイテンシ。** 正規表現/チェックサム層は純粋 CPU で < 1 ms per KB。NER 層は optional、CPU で < 100 ms per ~100 tokens
5. **検出しても保持しない。** fuseji は PII を at rest で持たない。任意の仮名化バウルトは in-memory で呼び出し側所有。これはマイナンバー（番号法）対応として重要: fuseji は _検出と破棄_ をするが、_番号を取り扱わない_
6. **公開でベンチマーク。** 合成された日本語 PII 評価データセットと再現可能な評価ハーネスを同梱。各リリースでエンティティ別の precision/recall を公開

## 3. 非ゴール（v0.x）

- ガードレール（プロンプトインジェクション、毒性）—マスキングのみ
- 画像 / PDF redaction
- PII の可逆暗号化（バウルトはセッション単位の仮名化であり暗号ではない）
- ストリーミングのトークン単位マスキング（事後の span マスキングのみ）
- 日本語 + ASCII パターン以外の言語

## 4. エンティティカバレッジ

### v0.1（リリース時）

| エンティティ種別 | 検出方式 | 備考 |
| --- | --- | --- |
| `MY_NUMBER` | 正規表現 + チェックディジット | 12 桁、公開チェックサム仕様、全/半角対応 |
| `JP_PHONE_NUMBER` | 正規表現 + numbering plan 検証 | 携帯（070/080/090）、固定電話、0120/0570、ハイフン・空白・全角変種 |
| `JP_POSTAL_CODE` | 正規表現 + コンテキスト語 | `〒` と `123-4567` 形式、7 桁数字の偽陽性を抑える文脈ブースト |
| `EMAIL` | 正規表現 | RFC-lite |
| `CREDIT_CARD` | 正規表現 + Luhn | ロケール非依存 |
| `PERSON` | NER（optional extra） | GiNZA バックエンド、`Recognizer` プロトコルの背後 |

### v0.3 以降（候補）

- `JP_ADDRESS` — 難物。正規化優先戦略（全/半角統一、丁目/番地/号 variant）の後にパターンマッチ。`jageocoder` / normalize-japanese-addresses 系のアプローチを評価
- `CORPORATE_NUMBER`（法人番号、opt-in: 公開情報だがクライアントによっては要マスク）
- `BANK_ACCOUNT_JP`、`DRIVERS_LICENSE_JP`
- 差し替え可能な NER バックエンド: GiNZA vs Japanese BERT NER vs 日本語合成 PII での GLiNER fine-tune の比較ベンチマーク

## 5. コア API

公開面は意図的に小さい: 1 エンジン、1 結果型、1 プロトコル。

```python
from fuseji import Masker

masker = Masker()  # 正規表現 + チェックサム認識器、モデルダウンロードなし

result = masker.mask("山田太郎さん(連絡先: 090-1234-5678, taro@example.co.jp)")

result.text
# "<PERSON_1>さん(連絡先: <JP_PHONE_NUMBER_1>, <EMAIL_1>)"

result.entities
# (Entity(type="PERSON", text="山田太郎", start=0, end=4, score=0.92, recognizer="ginza"),
#  Entity(type="JP_PHONE_NUMBER", ...), Entity(type="EMAIL", ...))
```

### 5.1 型

```python
@dataclass(frozen=True, slots=True)
class Entity:
    type: str          # "MY_NUMBER", "JP_PHONE_NUMBER", ...
    text: str          # マッチした表層形
    start: int         # 元テキストへのコードポイントオフセット
    end: int
    score: float       # 0.0–1.0 の信頼度
    recognizer: str    # 発火した認識器名

@dataclass(frozen=True, slots=True)
class MaskResult:
    text: str                  # マスク済みテキスト
    entities: tuple[Entity, ...]
    mapping: Mapping[str, str] # placeholder → 元（vault または戦略が出力した場合のみ非空）
```

### 5.2 エンジン

```python
class Masker:
    def __init__(
        self,
        recognizers: Sequence[Recognizer] | None = None,  # None = デフォルトセット
        ner: NerBackend | None = None,        # 例: GinzaBackend()。None = regex-only
        strategy: MaskStrategy | None = None,  # Placeholder（既定）/ Redact / Hash
        threshold: float = 0.4,               # recall 寄りデフォルト
        vault: Vault | None = None,           # 決定的な復元を有効化
        max_json_depth: int = 100,            # mask_json の再帰深度上限（fail-closed）
        mask_dict_keys: bool = False,         # mask_json で dict キーもマスク（v0.2、opt-in）
    ): ...

    def mask(self, text: str) -> MaskResult: ...
    def mask_json(self, data: Any) -> Any:    # dict/list/str を再帰
    def detect(self, text: str) -> tuple[Entity, ...]: ...  # マスクなしの検出
```

検出と匿名化（`strategy`）は Presidio 風に分離されているが、1 つのファサードの背後にあります。多くのユーザーは `mask` だけを呼びます。v0.2 で `Masker.detect` は内部で `normalize(text)` を 1 回だけ計算し、各認識器の `analyze(text, normalized=...)` に渡すことで重複正規化を排除しています。

### 5.3 Recognizer プロトコル（拡張性）

```python
class Recognizer(Protocol):
    entity_type: str        # 種別名（例: "EMAIL"）
    name: str               # 認識器の識別子（snake_case）、Entity.recognizer に格納
    def analyze(
        self, text: str, *, normalized: str | None = None
    ) -> Iterator[Entity]: ...
```

`normalized` は Masker 層が事前計算した正規化済みテキスト。正規化を必要としない認識器（例: EMAIL）はこの引数を無視してよいが、シグネチャ上は受け取る必要があります（v0.2 で破壊的変更）。

カスタム認識器（社員 ID、社内アカウント番号）は first-class:

```python
from fuseji.recognizers.base import regex_analyze  # 共通テンプレート（v0.2）

class EmployeeIdRecognizer:
    entity_type = "EMPLOYEE_ID"
    name = "employee_id"
    def analyze(self, text, *, normalized=None):
        return regex_analyze(
            text,
            entity_type=self.entity_type,
            recognizer_name=self.name,
            pattern=re.compile(r"E\d{6}"),
            normalized=normalized,
            default_score=0.9,
        )

masker = Masker(recognizers=[*default_recognizers(), EmployeeIdRecognizer()])
```

### 5.4 仮名化バウルト（optional）

```python
vault = InMemoryVault()                       # 8 文字 hex nonce を自動生成
masker = Masker(vault=vault)
r = masker.mask("田中さんと佐藤さん")
# -> <PERSON_1_a3f9b2c4>さんと<PERSON_2_a3f9b2c4>さん
restored = vault.restore(llm_response)        # 自分の nonce を含む placeholder のみ復元
```

同一表層形 ⇒ vault セッション内で同一 placeholder。マルチターン参照が一貫して維持されます。Vault は in-memory のみ、永続化は明示的に呼び出し側責任。

**セキュリティ既定**:
- `InMemoryVault.DEFAULT_EXCLUDED_TYPES` = `{MY_NUMBER, CREDIT_CARD}`。番号法 + PCI DSS 整合で復元不可
- placeholder にインスタンス固有 nonce が付き、別 Vault 由来の placeholder は構造的に restore で素通し（クロステナント漏洩防止、v0.2）
- `max_size=N` でメモリ使用量を有界化（FIFO eviction、長時間稼働の DoS 緩和）
- `assign_many(pairs)` で k 件の lock 取得を 1 件に縮約（VaultStrategy.mask の並列耐性）

## 6. 連携アダプタ

### 6.1 Langfuse SDK の mask 関数

```python
from fuseji.integrations.langfuse import make_mask_fn
from langfuse import Langfuse

langfuse = Langfuse(mask=make_mask_fn())  # str/dict/list の再帰 + エラーハンドリング
```

例外時は fail-closed: `"[fuseji: masking failed]"` を返し、原データを通しません。

### 6.2 Langfuse self-hosted ingestion masking callback / OTel Collector サイドカー

`[server]` extra で同じ FastAPI アプリを起動:

```bash
pip install 'fuseji[server]'
uvicorn fuseji.server.app:app --host 0.0.0.0 --port 8000
```

エンドポイント:
- `POST /mask` — 任意 JSON を再帰マスク
- `POST /detect` — テキストから entity 一覧
- `GET /healthz`

OpenAPI スキーマは `/openapi.json`。

**1 つのエンジン、3 つの入口。** アダプタには検出ロジックを含めず、すべて Masker に委譲。

## 7. リポジトリレイアウト

```
fuseji/
├── pyproject.toml            # uv 管理、extras: [ginza], [server], [all]
├── README.md / README.en.md
├── SECURITY.md
├── CHANGELOG.md
├── LICENSE                   # Apache-2.0
├── CONTRIBUTING.md
├── docs/
│   ├── design.md             # 本ファイル
│   └── api.md                # 公開 API リファレンス
├── src/fuseji/
│   ├── __init__.py           # Masker, Entity, MaskResult 等の re-export
│   ├── engine.py             # Masker、_resolve_overlaps
│   ├── types.py              # Entity, MaskResult
│   ├── strategies.py         # MaskStrategy + Placeholder / Redact / Hash / VaultStrategy
│   ├── vault.py              # Vault プロトコル + InMemoryVault（nonce / max_size / assign_many）
│   ├── entity_types.py       # EMAIL / MY_NUMBER 等の型定数
│   ├── exceptions.py         # FusejiError 階層
│   ├── recognizers/
│   │   ├── base.py           # Recognizer プロトコル + regex_analyze 共通テンプレート
│   │   ├── my_number.py
│   │   ├── jp_phone.py
│   │   ├── jp_postal.py
│   │   ├── email.py
│   │   └── credit_card.py
│   ├── ner/
│   │   ├── base.py           # NerBackend プロトコル
│   │   └── ginza.py          # [ginza] extra
│   ├── integrations/
│   │   └── langfuse.py       # Langfuse SDK アダプタ (fail-closed)
│   └── server/               # [server] extra
│       └── app.py            # create_app() + BodySizeLimit / ApiKeyAuth / RequestTimeout middleware
├── tests/
└── .github/workflows/ci.yml  # ruff + mypy + pytest マトリクス
```

正規表現コアは **ゼロ重量依存**。GiNZA/spaCy と FastAPI は extras に分離。

## 8. 評価計画（fuseji-bench）

v0.2 で `tests/bench/` 配下に整備済み（Masker パイプライン / 認識器単体 / `_replace_spans` / `Vault.restore` / `_resolve_overlaps` / `mask_json` / Strategies 横並び の 7 系統、計 38 ベンチケース）。CI には `bench (informational)` ジョブとして組み込み、`tests/test_latency_regression.py` で O(n²) 回帰の即時検知（`CI_PERF=1` の専用ジョブで実行）。

- 完全合成: Faker-ja + 厳選名前リストによる架空人名、生成住所、チェックサム有効だが架空のマイナンバー。スクレイプ実 PII は使わない
- テンプレベース生成 + 表層形摂動: 全/半角、ハイフン variant、敬語コンテキスト（様/さん/殿）、敵対的負例（人名を含む企業名、7 桁の非郵便番号、製品コード）
- 指標: エンティティ別 precision / recall / F1（span 単位、部分一致クレジットは別途報告）、KB あたり p50/p95 レイテンシ
- 同じデータで他ツール（Presidio + ja_core_news_trf、LLM Guard、GLiNER 変種）もスコアリングできるよう、データセットとハーネスをバージョン管理して公開

## 9. ロードマップ

**v0.1（PyPI 公開済み）**: 正規表現/チェックサム認識器（マイナンバー、JP 電話、郵便、メール、クレジットカード）・GiNZA PERSON（extra）・Placeholder/Redact/Hash 戦略・Vault・Langfuse SDK アダプタ・FastAPI サーバー・CI・README/SECURITY/CHANGELOG。

**v0.2（開発完了、次リリース予定）**: Recognizer プロトコル拡張（`name` + `regex_analyze` ファクトリ、normalized 正式化）・セキュリティ強化（Vault placeholder nonce / Hash mapping opt-in + length 16 / CC を Vault DEFAULT_EXCLUDED に追加 / API キー認証 + CORS opt-in / pure-ASGI chunked-body limit / mask_json dict key opt-in）・性能改善（Masker 層 normalize 1 回化 / Vault.assign_many bulk / _resolve_overlaps 早期採用 / Hash LRU opt-in）・テスト品質（doctest 統合 + coverage gate 90% / Unicode 境界 / クロス認識器 / bench 拡充）。Breaking Changes 5 件、CHANGELOG に移行ガイド付き。

**v0.3（候補）**: `JP_ADDRESS` 正規化優先検出（jageocoder / normalize-japanese-addresses 系の評価）・`CORPORATE_NUMBER`（法人番号）・Faker 戦略・ingestion-callback の Docker イメージ・OTel example。

**v0.4+（候補）**: NER バックエンド比較（GiNZA vs BERT-NER vs GLiNER-ja fine-tune）を fuseji-bench で公開・構造化フィールド対応マスキング（JSON キー保持）・span processor 向け batch API・true sweep-line `_resolve_overlaps`（worst-case O(n log n)）。

**Later / エコシステム**: Presidio に Japan recognizer pack を upstream（`JP_MY_NUMBER` 等）・LLM Guard backend 連携・バイリンガル docs サイト。

## 10. リスクと緩和

- **住所検出は本当に難しい。** v0.2 へ先送り。v0.1 の README で対応範囲を正直に表記。住所の recall を過大表明するのは除外より悪い
- **マイナンバーの法的センシティビティ（番号法）。** README / SECURITY.md / docs で明示: fuseji は in-flight で検出・マスクし、検出した番号を保存・ログ・転送しない。Vault は MY_NUMBER をデフォルト除外
- **NER のレイテンシ/フットプリント。** 厳格に optional extra。正規表現コア単体で意味ある v0.1
- **競合する商用プレイヤー（JP 特化のマスキング API/モデル）。** 需要を裏付ける存在。fuseji はセルフホスト性、透明性、ベンチマークの公開度で勝負 — まさに規制下の日本企業が必要とするもの
- **単独メンテナの持続性。** 小さな公開 API、ゼロ依存コア、孤立した認識器モジュール ⇒ コミュニティ PR のレビュー面が小さい。テストテンプレ付きの新認識器を good-first-issue として種まき
