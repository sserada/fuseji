# OpenTelemetry + fuseji 連携

OTel の `gen_ai.prompt` / `gen_ai.completion` 属性に含まれる PII を fuseji でマスクする 2 つの構成を示す。

## 推奨: SDK 統合（最も portable、外部依存最小） — `main.py` / `mask_processor.py`

OTel SDK の `SpanProcessor` として fuseji を組み込む方式。BatchSpanProcessor より手前で
属性を fuseji.Masker に通すだけで `gen_ai.prompt` / `gen_ai.completion` 等が
ローカル処理でマスクされる。Collector 経由の HTTP forward が不要で、デプロイ複雑度が
最小。

### 実行手順

```bash
pip install -r requirements.txt
python main.py
```

`ConsoleSpanExporter` の出力で `gen_ai.prompt` / `gen_ai.completion` 属性が
マスク済み (`<EMAIL_1>` / `<JP_PHONE_NUMBER_1>` 等) になることを確認。

### 自分のアプリへの組み込み

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from mask_processor import FusejiMaskingSpanProcessor

provider = TracerProvider()
provider.add_span_processor(FusejiMaskingSpanProcessor())  # 先に登録（export 直前にマスク）
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
```

### 制約

- `Span.set_attribute` を使って書き戻すため、OTel SDK の標準 Span 実装に依存
- Collector 経由で他チームのアプリ全部に強制マスクするには不向き → 下の Collector 構成へ

## 補助: OTel Collector 経由（拡張運用向け） — `otel-collector-config.yaml`

サービスメッシュ全体で強制マスクしたい場合の参考構成。

```
[App] --OTLP--> [OTel Collector] --(custom processor)--> [Langfuse / OTLP / 任意の backend]
```

### 注意点

- OTel Collector のビルトイン processor では HTTP forward を直接表現できない。
  Collector 内で fuseji を呼ぶには:
  1. **カスタム Go processor** を書いて `processors/` に追加（重い）
  2. **Lambda hook / Sidecar pattern** で外部 endpoint に飛ばす（インフラ依存）
  3. **fuseji-server を sidecar として起動し、上位 SDK で wrap** （実質的に SDK 統合に戻る）

実運用ではアプリ側の SDK 統合（上記）を選ぶか、自前カスタム processor を書くかの判断が必要。同梱の `otel-collector-config.yaml` は属性 **削除** のフォールバック例（マスクではなく drop）として残してある。

## fuseji-server を別途立てる構成

外部チームのアプリにも一括でマスクをかけたい場合、`examples/langfuse_ingestion_callback/` の docker-compose を参考に fuseji-server を立て、Langfuse の `mask` callback 経由で呼ぶ構成を採るのが現実的。
