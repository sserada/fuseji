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
    entity_type: str  # 種別名（例: "ZIP_CODE_US"）
    name: str         # 認識器の識別子（snake_case）。Entity.recognizer に格納
    def analyze(self, text: str) -> Iterable[Entity]: ...
```

regex + 任意の検証ロジックで完結する認識器は、`regex_analyze` 共通テンプレートを
使うとボイラープレートを大幅に削減できます：

```python
import re
from fuseji.recognizers.base import normalize, regex_analyze

_US_ZIP_PATTERN = re.compile(r"\d{5}(?:-\d{4})?")


class UsZipRecognizer:
    """US ZIP コード認識器。"""

    entity_type = "ZIP_CODE_US"
    name = "us_zip"

    def analyze(self, text):
        return regex_analyze(
            text,
            entity_type=self.entity_type,
            recognizer_name=self.name,
            pattern=_US_ZIP_PATTERN,
            default_score=0.9,
            # 検証関数を渡す場合（None を返すと候補を除外）
            # validate=my_validator,
            # 前処理で正規化したい場合
            # normalize_fn=normalize,
            # 前後が数字なら除外（ID の一部とみなす）
            # require_digit_boundary=True,
            # validate に渡す前にハイフン・空白を除去
            # strip_separators_before_validate=True,
        )
```

ビルトイン認識器（`email`, `credit_card`, `my_number`, `jp_phone`）はすべて
このテンプレートで実装されています（参考: `src/fuseji/recognizers/`）。

テストには全角/半角バリエーション、コンテキスト語の有無、偽陽性ケースを含めてください。

## ライセンス

コントリビューションは Apache-2.0 ライセンスの下で提供されます。
