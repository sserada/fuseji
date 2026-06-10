# fuseji 開発ガイド

## プロジェクト概要

fuseji (伏せ字) — 日本語特化のPII検出・マスキングミドルウェア（LLMオブザーバビリティ向け）。
Python 3.10+、`uv` でパッケージ管理。

## 開発フロー

1. GitHub Issue を作成し、タスクを記述する
2. `main` からブランチを作成する: `feat/<issue番号>-<短い説明>`, `fix/<issue番号>-<短い説明>`, `chore/<issue番号>-<短い説明>`
3. 開発・コミット
4. Issue を参照する PR を `main` に対して作成する
5. レビュー後にマージ

`main` への直接 push は禁止。必ず PR を経由すること。

## コマンド

```bash
uv sync                          # 依存関係のインストール
uv run ruff check src/ tests/    # リント
uv run ruff format src/ tests/   # フォーマット
uv run mypy src/                 # 型チェック
uv run pytest                    # テスト実行
```

## コード規約

- ソースレイアウト: `src/fuseji/`
- 公開APIには型アノテーション必須
- docstring・コメントは日本語
- Issue・PR・コミットメッセージは日本語

## ディレクトリ構成

```
src/fuseji/
├── engine.py          # Maskerエンジン
├── types.py           # Entity, MaskResult
├── strategies.py      # Placeholder / Redact / Hash
├── vault.py           # 仮名化バウルト
├── recognizers/       # PII認識器
├── ner/               # NERバックエンド
├── integrations/      # 外部サービス連携
└── server/            # FastAPIサーバー
```
