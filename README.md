# fuseji（伏せ字）

**日本語特化の PII 検出・マスキングミドルウェア — LLM オブザーバビリティ向け。**

[![CI](https://github.com/sserada/fuseji/actions/workflows/ci.yml/badge.svg)](https://github.com/sserada/fuseji/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

[English](README.en.md) | 日本語

---

## なぜ fuseji か

LLM オブザーバビリティ基盤（Langfuse、LangSmith、Phoenix、OTel）はトレース送信前に PII を伏せるためのマスキングフックを提供しています。しかし、既存の参照実装はすべて英語圏向けで、日本語テキストでは構造的に取りこぼします。

| ツール | 日本語対応 | マイナンバー | 日本の電話番号 |
| --- | --- | --- | --- |
| Presidio | ✗（recognizer 未提供） | ✗ | ✗（他ロケールの偶発一致のみ） |
| LLM Guard | ✗（英語 BERT 前提） | ✗ | ✗ |
| GLiNER PII | ✗（欧州 6 言語） | ✗ | ✗ |
| OTel Collector | ✗（regex のみ） | ✗ | ✗ |
| **fuseji** | **✓** | **✓**（番号法対応） | **✓** |

日本語固有の課題（語境界がない、住所が大→小の順序、全角/半角混在、人名と一般名詞の曖昧性、マイナンバーの 12 桁構造）に正面から対応します。

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

### v0.2 以降

- `JP_ADDRESS`（正規化ベースの住所検出）
- `CORPORATE_NUMBER`（法人番号、opt-in）
- `BANK_ACCOUNT_JP`、`DRIVERS_LICENSE_JP`
- NER バックエンド比較（GiNZA / BERT-NER / GLiNER-ja）

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

vault = InMemoryVault()  # MY_NUMBER はデフォルトで復元不可（番号法対応）
masker = Masker(vault=vault)

r1 = masker.mask("田中さんと佐藤さん")          # <PERSON_1>さんと<PERSON_2>さん（GiNZA 有効時）
r2 = masker.mask("田中さんに連絡して")          # <PERSON_1>さんに連絡して（一貫性維持）

# LLM 応答から復元
restored = vault.restore("<PERSON_1>さんへ返信しました")
# 田中さんへ返信しました
```

### マスキング戦略

```python
from fuseji import Masker, Placeholder, Redact, Hash

Masker(strategy=Placeholder())  # <EMAIL_1> 形式（デフォルト）
Masker(strategy=Redact())       # [REDACTED]
Masker(strategy=Hash(length=8)) # SHA256 ハッシュ先頭 8 文字
```

## Langfuse SDK 連携

```python
from langfuse import Langfuse
from fuseji.integrations.langfuse import make_mask_fn

langfuse = Langfuse(mask=make_mask_fn())
# 以降、すべてのトレースが fuseji で自動マスクされる
```

例外時は **fail-closed** で `[fuseji: masking failed]` を返し、原データは絶対に通しません。

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

- **v0.1**（現行）: 正規表現/checksum 認識器、GiNZA PERSON、Placeholder/Redact/Hash 戦略、Vault、Langfuse SDK アダプタ、FastAPI サーバー、CI
- **v0.2**: `JP_ADDRESS`、ingestion callback の Docker イメージ、OTel example、Faker 戦略、fuseji-bench
- **v0.3**: NER バックエンド比較（BERT-NER / GLiNER-ja fine-tune）、構造化フィールド対応、batch API

## コントリビューション

[CONTRIBUTING.md](CONTRIBUTING.md) を参照。認識器の追加は first-class でサポートされており、`Recognizer` プロトコル + テストの 2 点セットで提案できます。

## ライセンス

Apache-2.0 — [LICENSE](LICENSE) を参照。
