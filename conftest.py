"""ルート conftest — オプショナル依存が不在のとき該当モジュールを doctest 収集から除外する。

`pytest --doctest-modules` で `src/fuseji` 配下の docstring を実行する際、
`[server]` / `[ginza]` extra が未インストールの環境（CI の core matrix 等）では
`fastapi` / `spacy` の import エラーで collection が失敗する。

`collect_ignore_glob` でそれらのモジュールを動的に除外することで、core 環境でも
通常テストと公開 API の doctest を両立できる。
"""

from __future__ import annotations

import importlib.util

collect_ignore_glob: list[str] = []

# server/__init__.py が `from .app import app` で fastapi を eager import するため、
# パッケージ単位で除外する。
if importlib.util.find_spec("fastapi") is None:
    collect_ignore_glob.append("src/fuseji/server/*")
    collect_ignore_glob.append("src/fuseji/server")

# ner/ginza.py は TYPE_CHECKING で spacy を import しているが、GinzaBackend の
# `_load_nlp` で spacy.load を呼ぶため import 自体は通る。ただし spacy 不在環境では
# モジュール level の doctest 収集時に依存解決が走るので保険として除外する。
if importlib.util.find_spec("spacy") is None:
    collect_ignore_glob.append("src/fuseji/ner/ginza.py")
