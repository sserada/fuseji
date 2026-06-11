# Langfuse SDK + fuseji

Langfuse SDK の `mask=` パラメータに fuseji を差し込み、トレース送信前に PII を自動マスクする最短サンプル。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 環境変数

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-xxxx
export LANGFUSE_SECRET_KEY=sk-lf-xxxx
export LANGFUSE_HOST=https://cloud.langfuse.com  # self-hosted の場合は適宜
```

## 実行

```bash
python main.py
```

実行後、Langfuse ダッシュボードの該当トレースを開くと、入力テキスト中の PII（メール / 電話 / 郵便番号）が `<EMAIL_1>` 等の placeholder に置き換わって表示されます。

## ポイント

- `make_mask_fn()` は内部で `Masker()` を生成。カスタム認識器や Vault を使いたい場合は `make_mask_fn(masker=Masker(...))` を渡す
- マスキング処理で例外が出た場合は **fail-closed** で固定 placeholder `[fuseji: masking failed]` が送られ、原データは Langfuse に絶対に送信されない
- マスクされるのは送信側のテキスト。実際の LLM への入力は元のまま（fuseji は in-flight masking のみ）
