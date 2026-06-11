"""PII 認識器サブパッケージ.

公開シンボルは `Recognizer` プロトコル、`default_recognizers()` ファクトリ、
そして主要正規化関数 `normalize` の 3 つ。`regex_analyze` ヘルパや
`normalize_digits` / `normalize_hyphens` などのビルトイン認識器内部実装の
ユーティリティは、`from .base import ...` 経由で個別に import すること
（外部 API 安定性の保証対象外）。
"""

from .base import Recognizer, default_recognizers, normalize

__all__ = ["Recognizer", "default_recognizers", "normalize"]
