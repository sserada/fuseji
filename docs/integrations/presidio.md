# Presidio 統合 (`fuseji.integrations.presidio`)

Microsoft Presidio (`presidio-analyzer`) との統合アダプタ (#147)。fuseji の日本語特化認識器を Presidio の `EntityRecognizer` として登録し、Presidio エコシステム（Langfuse / LangSmith の標準統合、社内 PII パイプライン）から呼び出せるようにする。

## インストール

```bash
pip install 'fuseji[presidio]'
```

`[presidio]` extra は `presidio-analyzer>=2.2.0` を引きます。Presidio 本体は spaCy ベースの NLP エンジンを必要とするため、ja 用 spaCy モデル（例: `ja_core_news_sm`）は別途インストールしてください。

## 使い方

### 一括登録

```python
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from fuseji.integrations.presidio import register_fuseji_recognizers

# Presidio に ja の NLP エンジンを設定（spaCy ja モデル必須）
nlp_config = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "ja", "model_name": "ja_core_news_sm"}],
}
nlp_engine = NlpEngineProvider(nlp_engine_configuration=nlp_config).create_engine()
analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["ja"])

# fuseji 認識器を一括登録（default + opt-in 全件）
register_fuseji_recognizers(analyzer)

results = analyzer.analyze(text="マイナンバー: 123456789018", language="ja")
# [RecognizerResult(entity_type='JP_MY_NUMBER', start=8, end=20, score=0.95, ...)]
```

### 認識器を絞って登録

```python
from fuseji.recognizers.my_number import MyNumberRecognizer
from fuseji.recognizers.jp_phone import JpPhoneRecognizer

register_fuseji_recognizers(
    analyzer,
    recognizers=[MyNumberRecognizer(), JpPhoneRecognizer()],
)
```

### 個別アダプタを構築（高度な用途）

`AnalyzerEngine` への登録経路を自前で持っているケース（カスタム registry / DI コンテナ）では、`fuseji_to_presidio_recognizer` で 1 つずつ変換できます。

```python
from fuseji.integrations.presidio import fuseji_to_presidio_recognizer
from fuseji.recognizers.corporate_number import CorporateNumberRecognizer

adapter = fuseji_to_presidio_recognizer(
    CorporateNumberRecognizer(),
    supported_language="ja",
    entity_name="JP_CORPORATE_NUMBER",  # 省略時は自動マッピング
)
analyzer.registry.add_recognizer(adapter)
```

## エンティティ名マッピング

fuseji の entity type と Presidio に登録される `entity_type` の対応。日本語専用 type は `JP_*` 接頭辞で名前空間衝突を避けます。

| fuseji | Presidio 上の名前 |
| --- | --- |
| `EMAIL` | `EMAIL_ADDRESS`（Presidio 既定名と整合） |
| `CREDIT_CARD` | `CREDIT_CARD`（Presidio 既定名と一致） |
| `MY_NUMBER` | `JP_MY_NUMBER` |
| `CORPORATE_NUMBER` | `JP_CORPORATE_NUMBER` |
| `JP_PHONE_NUMBER` | `JP_PHONE_NUMBER` |
| `JP_POSTAL_CODE` | `JP_POSTAL_CODE` |
| `JP_ADDRESS` | `JP_ADDRESS` |
| `PERSON`（GiNZA 等 NER 経由） | `PERSON`（Presidio 既定名と一致） |

`fuseji_to_presidio_recognizer(..., entity_name="...")` で任意の名前に上書きできます。

## 設計上の注意

- fuseji の認識器は `nlp_artifacts` に依存しないため、`analyze()` 経由でも spaCy 経由のトークン化を必要としません（既存の Presidio 認識器との同居は問題なし）
- Presidio 側の `decision_process` や `analysis_explanation` は本アダプタでは付与しません。詳細な根拠が必要な場合は `RecognizerResult.analysis_explanation` を自前で構築してください
- マイナンバー (`MY_NUMBER`) は番号法対応のため、Presidio 経由でも fuseji 側のチェックディジット検証ロジックが使われます。score 0.5 (チェックディジット不一致) も recall 優先で返ります

## 例

`examples/presidio/` も参照してください（実行可能サンプル）。
