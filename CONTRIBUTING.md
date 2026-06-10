# コントリビューションガイド

fuseji への貢献に感謝します。

## 開発環境のセットアップ

```bash
# リポジトリをクローン
git clone https://github.com/sserada/fuseji.git
cd fuseji

# 依存関係をインストール（uv が必要）
uv sync --all-extras
```

## 開発フロー

1. Issue を作成し、やることを記述する
2. `main` からブランチを作成する
   - 機能追加: `feat/<issue番号>-<短い説明>`
   - バグ修正: `fix/<issue番号>-<短い説明>`
   - その他: `chore/<issue番号>-<短い説明>`
3. 開発・コミット
4. PR を作成し、関連 Issue を参照する

## コマンド

```bash
uv run ruff check src/ tests/    # リント
uv run ruff format src/ tests/   # フォーマット
uv run mypy src/                 # 型チェック
uv run pytest                    # テスト
```

## コード規約

- docstring・コメントは日本語
- 公開 API には型アノテーション必須
- PR 前にリント・型チェック・テストをすべて通すこと

## 認識器の追加

新しい PII 認識器の追加は歓迎します。`Recognizer` プロトコルを実装してください：

```python
class Recognizer(Protocol):
    entity_type: str
    def analyze(self, text: str) -> Iterable[Entity]: ...
```

テストには全角/半角バリエーション、コンテキスト語の有無、偽陽性ケースを含めてください。

## ライセンス

コントリビューションは Apache-2.0 ライセンスの下で提供されます。
