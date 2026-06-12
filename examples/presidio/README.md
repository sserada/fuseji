# Presidio 統合サンプル (#147)

fuseji の日本語特化認識器を Microsoft Presidio (`AnalyzerEngine`) から呼ぶサンプル。

## セットアップ

```bash
pip install 'fuseji[presidio]'
# spaCy の ja モデルを別途取得（Presidio が language="ja" で要求するため）
python -m spacy download ja_core_news_sm
```

## 実行

```bash
python examples/presidio/run.py
```

出力例:

```
JP_MY_NUMBER (score=0.95) at 8-20: 123456789018
JP_PHONE_NUMBER (score=0.85) at 27-40: 090-1234-5678
EMAIL_ADDRESS (score=1.0) at 47-63: taro@example.com
```

## 何が起きているか

1. `register_fuseji_recognizers(analyzer)` が fuseji の認識器を Presidio の `EntityRecognizer` として一括登録
2. fuseji 側の認識器は Pure-Python regex + checksum なので追加の重い依存はゼロ
3. Presidio 側の他言語認識器（英語 SSN / IBAN 等）とも共存可能

## 参考

- `docs/integrations/presidio.md` — API と設計上の注意
- `src/fuseji/integrations/presidio.py` — アダプタ実装
