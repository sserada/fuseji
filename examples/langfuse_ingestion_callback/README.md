# Langfuse self-hosted + fuseji-server を ingestion masking callback として使う

Langfuse self-hosted の ingestion masking 機能から fuseji-server を呼び、すべての SDK / OpenLLMetry / OpenLIT 経由のトレースに対し PII マスクを強制する構成。

## アーキテクチャ

```
[Any LLM client] --traces--> [Langfuse worker] --POST /mask--> [fuseji-server]
                                                         ↓
                                            masked JSON が Langfuse に保存
```

SDK 側でアダプタを差し込めない（third-party 計装の場合など）でも、Langfuse 取り込み層で一括マスク。

## セットアップ

```bash
docker compose up -d
```

これで以下が起動:
- `fuseji-server`（port 8000、`/mask` `/detect` `/healthz` を提供）

## Langfuse self-hosted への組み込み

Langfuse self-hosted の環境変数で ingestion masking のエンドポイントを指定:

```env
LANGFUSE_MASKING_ENDPOINT=http://fuseji-server:8000/mask
```

（具体的な変数名は使用する Langfuse バージョンの公式ドキュメントを参照。本サンプルでは fuseji 側の最小構成のみ提供。）

## 動作確認

```bash
curl -X POST http://localhost:8000/mask \
  -H 'Content-Type: application/json' \
  -d '{"data": "メール: taro@example.co.jp、電話: 090-1234-5678"}'
# => {"data":"メール: <EMAIL_1>、電話: <JP_PHONE_NUMBER_1>"}

curl http://localhost:8000/healthz
# => {"status":"ok"}
```

## ポイント

- fuseji-server には検出ロジックは含まれない（Masker に委譲）。本番運用では fuseji の dev タグではなく特定 version イメージを固定すること
- 高 RPS では FastAPI を gunicorn + uvicorn workers の構成で多重化し、運用上の上限値（body size / timeout / API キー認証 / CORS、いずれも v0.2 で実装済み）を必ず有効化:

  ```bash
  export FUSEJI_SERVER_MAX_BODY_BYTES=1000000   # 1MB（default）
  export FUSEJI_SERVER_TIMEOUT_SECONDS=30       # 30 秒（default）
  export FUSEJI_API_KEY=...                     # X-API-Key ヘッダで認証
  export FUSEJI_CORS_ORIGINS=https://langfuse.your-host.example
  ```
