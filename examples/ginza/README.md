# GiNZA バックエンドで日本人名（PERSON）も検出

正規表現認識器 + GiNZA NER を組み合わせ、自然文中の人名も検出する例。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

初回実行時に GiNZA モデル（`ja_ginza`）のダウンロードが発生します（数百 MB）。

## 実行

```bash
python main.py
```

期待出力:

```
山田太郎 (PERSON, score=0.85)
taro@example.co.jp (EMAIL, score=1.0)
090-1234-5678 (JP_PHONE_NUMBER, score=0.95)

マスク結果:
<PERSON_1>さん(連絡先: <JP_PHONE_NUMBER_1>, <EMAIL_1>)
```

## ポイント

- `Masker(ner=GinzaBackend())` で GiNZA バックエンドを有効化
- デフォルト labels は `("Person",)`。`GinzaBackend(labels=("Person", "Province", "City"))` で地名等も検出可能
- レイテンシは CPU で約 100ms / 100 tokens。バッチ処理用途には fuseji-bench（Issue #27）で計測後にチューニング推奨
