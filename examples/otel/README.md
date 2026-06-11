# OTel Collector + fuseji-server

OTel Collector の `processors` 経由で fuseji-server の `/mask` を叩き、`gen_ai.prompt` / `gen_ai.completion` 等の属性に含まれる PII をマスクする構成。

## アーキテクチャ

```
[App] --OTLP--> [OTel Collector]
                     │
                     ├─ transform/attribute_processor
                     │     └─ HTTP forward to fuseji-server /mask
                     │
                     └─ exporter (Langfuse / OTLP / OpenTelemetry backend)
```

## セットアップ

1. fuseji-server を起動:

```bash
pip install 'fuseji[server]>=0.1.0'
uvicorn fuseji.server.app:app --host 0.0.0.0 --port 8000
```

2. OTel Collector を起動（同梱の `otel-collector-config.yaml` を参照）:

```bash
otelcol-contrib --config otel-collector-config.yaml
```

## ポイント

- OTel Collector のビルトイン processor では HTTP forward を直接表現できないため、本サンプルでは `transform/attribute_processor` でローカル処理を行う形を示している。本番では カスタム processor or Lambda 連携が必要
- fuseji-server の代わりに OpenTelemetry Collector 上で動く Python extension として `fuseji.Masker` を直接呼ぶ統合も可能（将来検討）
- gen_ai semantic conventions の `gen_ai.prompt` / `gen_ai.completion` がマスク対象
