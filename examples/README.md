# fuseji examples

各サブディレクトリは独立した最小サンプル。`pip` だけでセットアップでき、uv は不要。

| ディレクトリ | 説明 |
| --- | --- |
| [`langfuse_sdk/`](langfuse_sdk/) | Langfuse SDK の `mask=` パラメータに fuseji を差し込む最短サンプル |
| [`langfuse_ingestion_callback/`](langfuse_ingestion_callback/) | Langfuse self-hosted の ingestion masking callback として fuseji-server を使う |
| [`otel/`](otel/) | OpenTelemetry SDK 統合（`mask_attribute` helper で `gen_ai.prompt` 等を set 前マスク） + OTel Collector 経由の補助構成 |
| [`ginza/`](ginza/) | GiNZA バックエンド有効化で日本人名（PERSON）も検出 |
| [`presidio/`](presidio/) | Microsoft Presidio `AnalyzerEngine` に fuseji 認識器を `EntityRecognizer` として登録する統合サンプル |
| [`custom_recognizer/`](custom_recognizer/) | 自社専用 ID (社員番号 等) のカスタム `Recognizer` を実装して `Masker` に組み込む最小例 |

## 共通のセットアップ

各サンプルは独立した `requirements.txt` を持つ。Python 3.10+ の仮想環境で:

```bash
cd examples/<name>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
