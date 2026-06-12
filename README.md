# fuseji（伏せ字）

**日本語特化の PII 検出・マスキングミドルウェア — LLM オブザーバビリティ向け。**

[![CI](https://github.com/sserada/fuseji/actions/workflows/ci.yml/badge.svg)](https://github.com/sserada/fuseji/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

[English](README.en.md) | 日本語

---

## なぜ fuseji か

LLM オブザーバビリティ基盤（Langfuse、LangSmith、Phoenix、OTel）はトレース送信前に PII を伏せるためのマスキングフックを提供しています。しかし、既存の参照実装はすべて英語圏向けで、日本語テキストでは構造的に取りこぼします。

| ツール | 日本語対応 | マイナンバー | 日本の電話番号 | モデルサイズ | 推論コスト |
| --- | --- | --- | --- | --- | --- |
| Presidio | ✗（recognizer 未提供） | ✗ | ✗（他ロケールの偶発一致のみ） | regex + 任意 NER | ms |
| LLM Guard | ✗（英語 BERT 前提） | ✗ | ✗ | 数百MB BERT | 数十ms |
| GLiNER PII | ✗（欧州 6 言語） | ✗ | ✗ | 0.2B | 数十ms |
| OpenAI Privacy Filter | △（英語中心） | ✗ | ✗ | 1.5B 規模（活性 50M 級 MoE） | GPU 推論前提 |
| GLiNER2-PII | △（多言語、日本語特化なし） | ✗ | ✗ | 0.3B | CPU 推論可 |
| OTel Collector | ✗（regex のみ） | ✗ | ✗ | regex のみ | ms |
| **fuseji** | **✓** | **✓**（番号法対応） | **✓** | regex + 任意 NER | μs〜ms |

日本語固有の課題（語境界がない、住所が大→小の順序、全角/半角混在、人名と一般名詞の曖昧性、マイナンバーの 12 桁構造）に正面から対応します。

### 汎用 LLM ベース PII redactor との使い分け

近年、`OpenAI Privacy Filter` や `GLiNER2-PII` のような汎用 PII redactor が登場しています。fuseji とは設計目標が異なり、補完的に併用できます。

- **fuseji を選ぶ場面**: LLM オブザーバビリティのインライン経路で μs〜ms オーダーのレイテンシ予算しか取れない、GPU を持たないサイドカー / Edge / Lambda、マイナンバー / 法人番号 / 日本の住所など fail-closed が必要な番号法対応エンティティ、依存ゼロでデプロイしたい
- **汎用 LLM redactor を選ぶ場面**: 多言語の自由記述から想定外の PII を recall したい、GPU リソースに余裕がある、英語中心の社内ドキュメントを扱う
- **将来の併用**: fuseji の `recognizers=` インタフェースに `GLiNER2` / `Privacy Filter` をアダプタとして組み込む案を検討中（recall 向上の追加バックエンドとして）。Presidio との相互運用は [`fuseji.integrations.presidio`](https://github.com/sserada/fuseji/issues/147) で検討中

## 対応エンティティ

### v0.1（リリース時）

| Entity | 検出方式 | 備考 |
| --- | --- | --- |
| `MY_NUMBER` | 正規表現 + チェックディジット | 12 桁、総務省公開仕様、全角/半角対応、recall 優先 |
| `JP_PHONE_NUMBER` | 正規表現 + numbering plan 検証 | 携帯 070/080/090、フリーダイヤル 0120、ナビダイヤル 0570、固定電話 |
| `JP_POSTAL_CODE` | 正規表現 + コンテキストブースト | 〒 / `XXX-XXXX` 形式、文脈語で score 加重 |
| `EMAIL` | 正規表現 | RFC-lite |
| `CREDIT_CARD` | 正規表現 + Luhn 検証 | ロケール非依存 |
| `PERSON` | NER（GiNZA backend、`[ginza]` extra） | CPU で ~100ms / ~100 tokens |

### v0.3（実装済み）

- `JP_ADDRESS`（47 都道府県 + 市区町村 + 番地、minimum viable regex、opt-in）
- `CORPORATE_NUMBER`（法人番号 13 桁、国税庁公開仕様 checksum、opt-in）

### v0.4 以降（候補）

- `BANK_ACCOUNT_JP`、`DRIVERS_LICENSE_JP`
- NER バックエンド比較（GiNZA / BERT-NER / GLiNER-ja）
- `JP_ADDRESS` の高精度版（jageocoder / normalize-japanese-addresses 系を評価）

## インストール

```bash
# 正規表現コアのみ（ゼロ依存）
pip install fuseji

# GiNZA で人名（PERSON）検出も有効化
pip install 'fuseji[ginza]'

# FastAPI サーバー（/mask /detect /healthz）を有効化
pip install 'fuseji[server]'

# 全部入り
pip install 'fuseji[all]'
```

## クイックスタート

```python
from fuseji import Masker

masker = Masker()

result = masker.mask("山田さん(連絡先: 090-1234-5678, taro@example.co.jp、〒123-4567)")

print(result.text)
# 山田さん(連絡先: <JP_PHONE_NUMBER_1>, <EMAIL_1>、<JP_POSTAL_CODE_1>)

for e in result.entities:
    print(e.type, e.text, e.score)
# JP_PHONE_NUMBER 090-1234-5678 0.95
# EMAIL taro@example.co.jp 1.0
# JP_POSTAL_CODE 〒123-4567 0.95
```

### 仮名化バウルト（復元可能なマスキング）

```python
from fuseji import Masker, InMemoryVault

# MY_NUMBER と CREDIT_CARD はデフォルトで Vault 除外（番号法 + PCI DSS 整合、復元不可）
vault = InMemoryVault()
masker = Masker(vault=vault)

r1 = masker.mask("田中さんと佐藤さん")
# 例: 「<PERSON_1_a3f9b2c4>さんと<PERSON_2_a3f9b2c4>さん」(GiNZA 有効時)
r2 = masker.mask("田中さんに連絡して")
# 例: 「<PERSON_1_a3f9b2c4>さんに連絡して」(一貫性維持)

# LLM 応答（r1.text を含むテキスト）から復元
restored = vault.restore(r1.text)
# 田中さんと佐藤さん

# placeholder 末尾の nonce は Vault インスタンス固有（v0.2 で導入）。
# 別 Vault が生成した placeholder 形式は restore で素通しされ、
# クロステナント漏洩を構造的に防ぐ。
```

### マスキング戦略

```python
from fuseji import Masker, Placeholder, Redact, Hash

Masker(strategy=Placeholder())                       # <EMAIL_1> 形式（デフォルト）
Masker(strategy=Redact())                            # [REDACTED]
Masker(strategy=Hash())                              # SHA256 16 文字（v0.2 デフォルト、レインボー耐性）
Masker(strategy=Hash(length=8, keep_mapping=True))   # v0.1 互換: 8 文字 + 逆引き mapping
```

`[faker]` extra を追加すれば `FakerStrategy` でフォーマット保持のまま架空値に置換:

```python
from fuseji import Masker
from fuseji.faker_strategy import FakerStrategy  # pip install 'fuseji[faker]'

masker = Masker(strategy=FakerStrategy(salt="my-app-salt"))
result = masker.mask("田中さん a@b.com")
# 例: '林 陽子さん user@example.org' のように架空値に置換
# MY_NUMBER / CREDIT_CARD / CORPORATE_NUMBER は固定マスク <MASKED>
```

## Langfuse SDK 連携

```python
from langfuse import Langfuse
from fuseji.integrations.langfuse import make_mask_fn

langfuse = Langfuse(mask=make_mask_fn())
# 以降、すべてのトレースが fuseji で自動マスクされる
```

例外時は **fail-closed** で `[fuseji: masking failed]` を返し、原データは絶対に通しません。

## OpenTelemetry SDK 統合（`[otel]` extra）

```python
from opentelemetry import trace
from fuseji import Masker
from fuseji.integrations.otel import mask_attribute

masker = Masker()
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("llm-call") as span:
    mask_attribute(span, "gen_ai.prompt", user_prompt, masker)
```

詳細は [`docs/integrations/otel.md`](docs/integrations/otel.md)。

## Presidio 統合（`[presidio]` extra）

Microsoft Presidio から fuseji の日本語特化認識器を呼べます。

```python
from presidio_analyzer import AnalyzerEngine
from fuseji.integrations.presidio import register_fuseji_recognizers

analyzer = AnalyzerEngine(supported_languages=["ja"])  # ja の NLP engine を別途設定
register_fuseji_recognizers(analyzer)  # fuseji 認識器を一括登録
```

日本語専用 type は `JP_*` 接頭辞で Presidio 名前空間衝突を回避（`MY_NUMBER` → `JP_MY_NUMBER` 等）。詳細は [`docs/integrations/presidio.md`](docs/integrations/presidio.md)。

## サーバーモード（Langfuse 取り込みコールバック / OTel サイドカー）

```bash
pip install 'fuseji[server]'
uvicorn fuseji.server.app:app --host 0.0.0.0 --port 8000
```

```bash
# マスキング
curl -X POST http://localhost:8000/mask \
  -H 'Content-Type: application/json' \
  -d '{"data": "メール: taro@example.com"}'
# {"data": "メール: <EMAIL_1>"}

# 検出のみ
curl -X POST http://localhost:8000/detect \
  -H 'Content-Type: application/json' \
  -d '{"text": "電話 090-1234-5678"}'
# {"entities": [{"type": "JP_PHONE_NUMBER", ...}]}
```

OpenAPI スキーマ: `http://localhost:8000/openapi.json`

### 運用上の上限値・認証

| 制限 | デフォルト | 環境変数 / API | 超過時の挙動 |
| --- | --- | --- | --- |
| リクエストボディサイズ | 1 MB | `FUSEJI_SERVER_MAX_BODY_BYTES` / `create_app(max_body_bytes=...)` | HTTP 413 |
| 1 リクエストあたり処理時間 | 30 秒 | `FUSEJI_SERVER_TIMEOUT_SECONDS` / `create_app(timeout_seconds=...)` | HTTP 504 |
| `mask_json` 再帰深度 | 100 | `Masker(max_json_depth=...)` | `"[fuseji: too deep]"` で fail-closed |
| API キー認証 | 無認証 | `FUSEJI_API_KEY` / `create_app(api_key=...)` | `X-API-Key` 不一致で HTTP 401 |
| CORS 許可オリジン | CORS 無効 | `FUSEJI_CORS_ORIGINS` (カンマ区切り) / `create_app(cors_origins=...)` | 未許可オリジンは ACAO ヘッダなし |

> ⚠️ **インターネット公開時** は `FUSEJI_API_KEY` と `FUSEJI_CORS_ORIGINS` の両方を必ず設定すること。信頼境界内のサイドカー運用が前提。

## セキュリティ・法令上の注意

fuseji は **検出・破棄するが保持しない（detect, never retain）** ことを設計原則としています。

- 検出値はメモリ上のみで処理し、永続化しません
- `InMemoryVault` も session-scoped（プロセスメモリのみ）。永続化はユーザー側責任
- **マイナンバー（`MY_NUMBER`）は `Vault.DEFAULT_EXCLUDED_TYPES` でデフォルト除外** され、復元できません（番号法対応）
- Langfuse アダプタは例外時に fail-closed で原データを返しません

詳しくは [SECURITY.md](SECURITY.md) を参照してください。

> ⚠️ fuseji は **in-flight masking** のみ提供します。検出値の保持・ログ出力は呼び出し側の責任です。

## 設計と非ゴール

詳細は [docs/design.md](docs/design.md) を参照。

**v0.x の非ゴール**: ガードレール（プロンプトインジェクション、毒性）、画像/PDF redaction、可逆暗号、ストリーミング token-by-token マスキング、日本語以外の自然文（ASCII パターンは対応）。

## ロードマップ

詳細は [ROADMAP.md](ROADMAP.md) を参照してください。直近の変更履歴は [CHANGELOG.md](CHANGELOG.md)、設計討議は [docs/design.md §10](docs/design.md) にあります。

- **v0.1**（PyPI 公開済み）: 正規表現/checksum 認識器、GiNZA PERSON、Placeholder/Redact/Hash 戦略、Vault、Langfuse SDK アダプタ、FastAPI サーバー、CI
- **v0.2**（開発完了、次リリース予定）: Recognizer プロトコル拡張、セキュリティ強化、性能改善、品質向上
- **v0.3**（実装中、リリース予定）: `JP_ADDRESS` / `CORPORATE_NUMBER` 認識器（opt-in）、`FakerStrategy` / `[faker]`、OTel SDK 公式統合 (`[otel]`)、Presidio 公式アダプタ (`[presidio]`)、セキュリティ強化（`/detect` redact / repr PII safe / salt ランダム化 / mapping opt-in）
- **v0.4 以降**（候補）: NER バックエンド比較、構造化フィールド対応、batch API、true sweep-line `_resolve_overlaps`

## コントリビューション

[CONTRIBUTING.md](CONTRIBUTING.md) を参照。認識器の追加は first-class でサポートされており、`Recognizer` プロトコル + テストの 2 点セットで提案できます。

## ライセンス

Apache-2.0 — [LICENSE](LICENSE) を参照。
