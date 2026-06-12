"""Microsoft Presidio との統合アダプタ (#147).

fuseji の認識器を Presidio の ``EntityRecognizer`` として登録するためのアダプタ。
Presidio エコシステム（Langfuse / LangSmith の標準統合、社内 PII パイプライン）
から fuseji の日本語特化認識器（マイナンバー / 法人番号 / 日本の電話 / 郵便 /
住所）を呼べるようにする。

`[presidio]` extra でインストール:

```bash
pip install 'fuseji[presidio]'
```

使い方:

```python
from presidio_analyzer import AnalyzerEngine
from fuseji.integrations.presidio import register_fuseji_recognizers

analyzer = AnalyzerEngine()
register_fuseji_recognizers(analyzer)  # fuseji 認識器を一括登録

results = analyzer.analyze(text="マイナンバー: 123456789018", language="ja")
# Presidio の RecognizerResult として fuseji の結果が返る
```

**設計方針**:

- fuseji の `Recognizer` プロトコルは Presidio の `EntityRecognizer` よりもシンプル
  (`analyze(text)` のみ) なので、薄い変換アダプタで包む
- 各 fuseji entity type は対応する Presidio entity_type を持つ。日本語専用 type
  (`MY_NUMBER` / `JP_PHONE_NUMBER` 等) は Presidio に既存の対応がないため、fuseji
  独自の名前空間 (例: ``JP_MY_NUMBER``) として登録する。汎用 type (`EMAIL` /
  `CREDIT_CARD`) は Presidio 既定名と一致するため衝突しない名前を残す
- Presidio の言語パラメータは ``"ja"`` を主想定。fuseji は internally normalize で
  全半角混在を処理しているため、Presidio の ``nlp_artifacts`` には依存しない
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from ..entity_types import (
    CORPORATE_NUMBER,
    CREDIT_CARD,
    EMAIL,
    JP_ADDRESS,
    JP_PHONE_NUMBER,
    JP_POSTAL_CODE,
    MY_NUMBER,
)
from ..exceptions import InvalidConfigError
from ..recognizers.base import Recognizer, default_recognizers
from ..recognizers.corporate_number import CorporateNumberRecognizer
from ..recognizers.jp_address import JpAddressRecognizer

# fuseji の entity_type → Presidio で使う entity_type (#147)。
# Presidio に既存の汎用 type は同名を返し、日本語専用 type は ``JP_*`` 接頭辞で
# 名前空間衝突を避ける (Presidio 本体に upstream される際は本マップが互換層になる)。
_TYPE_MAP: dict[str, str] = {
    EMAIL: "EMAIL_ADDRESS",  # Presidio 既定名に合わせる
    CREDIT_CARD: "CREDIT_CARD",  # Presidio 既定名と一致
    MY_NUMBER: "JP_MY_NUMBER",
    CORPORATE_NUMBER: "JP_CORPORATE_NUMBER",
    JP_PHONE_NUMBER: "JP_PHONE_NUMBER",
    JP_POSTAL_CODE: "JP_POSTAL_CODE",
    JP_ADDRESS: "JP_ADDRESS",
    # PERSON は Presidio に既定があるが、fuseji default_recognizers() には NER が
    # 含まれないため、デフォルトの登録対象には入れない。明示的に登録したい場合は
    # `register_fuseji_recognizers(analyzer, recognizers=[ginza_backed_recognizer])`
    # 経路で渡す。
    "PERSON": "PERSON",
}


def _import_presidio() -> tuple[Any, Any]:
    """Presidio クラスを遅延 import する（optional dependency のため）."""
    try:
        from presidio_analyzer import EntityRecognizer, RecognizerResult
    except ImportError as e:
        msg = (
            "fuseji.integrations.presidio を使うには presidio-analyzer が必要です。"
            "`pip install fuseji[presidio]` でインストールしてください。"
        )
        raise InvalidConfigError(msg) from e
    return EntityRecognizer, RecognizerResult


def fuseji_to_presidio_recognizer(
    recognizer: Recognizer,
    *,
    supported_language: str = "ja",
    entity_name: str | None = None,
) -> Any:
    """fuseji の `Recognizer` を Presidio の `EntityRecognizer` に変換する (#147).

    Args:
        recognizer: fuseji 側の `Recognizer` プロトコルを実装したオブジェクト
        supported_language: Presidio の言語コード。デフォルト ``"ja"``。fuseji は
            internally normalize で全半角を扱うため、Presidio の言語ディスパッチ
            目的でのみ使う
        entity_name: 登録する Presidio 上の entity_type 名。省略時は
            `_TYPE_MAP` 経由で自動マッピング（``MY_NUMBER`` → ``JP_MY_NUMBER`` 等）

    Returns:
        Presidio の ``AnalyzerEngine`` に登録できる ``EntityRecognizer`` インスタンス
    """
    entity_recognizer_cls, recognizer_result_cls = _import_presidio()
    mapped = entity_name or _TYPE_MAP.get(recognizer.entity_type, recognizer.entity_type)

    class FusejiRecognizerAdapter(entity_recognizer_cls):  # type: ignore[misc, valid-type]
        """fuseji の ``Recognizer`` を Presidio の ``EntityRecognizer`` に変換するアダプタ."""

        def __init__(self) -> None:
            self._fuseji_recognizer = recognizer
            self._mapped_entity = mapped
            super().__init__(
                supported_entities=[mapped],
                supported_language=supported_language,
                name=f"fuseji_{recognizer.name}",
            )

        def load(self) -> None:
            # fuseji 認識器は __init__ で完結する Pure-Python 実装なので no-op
            return None

        def analyze(
            self,
            text: str,
            entities: Sequence[str],
            nlp_artifacts: Any = None,
        ) -> list[Any]:
            # Presidio から要求された entities に自分の対応 type が含まれない場合は
            # 早期 return（Presidio の他認識器との dispatch 整合性）
            if entities and self._mapped_entity not in entities:
                return []
            results: list[Any] = []
            for e in self._fuseji_recognizer.analyze(text):
                results.append(
                    recognizer_result_cls(
                        entity_type=self._mapped_entity,
                        start=e.start,
                        end=e.end,
                        score=e.score,
                    )
                )
            return results

    return FusejiRecognizerAdapter()


def register_fuseji_recognizers(
    analyzer: Any,
    recognizers: Iterable[Recognizer] | None = None,
    *,
    supported_language: str = "ja",
    include_opt_in: bool = True,
) -> list[Any]:
    """`AnalyzerEngine` に fuseji 認識器を一括登録する (#147).

    Args:
        analyzer: Presidio の ``AnalyzerEngine`` インスタンス
        recognizers: 登録する fuseji 認識器の iterable。省略時は
            `default_recognizers()` + (`include_opt_in=True` なら `JpAddressRecognizer` /
            `CorporateNumberRecognizer` も追加)
        supported_language: Presidio 言語コード。デフォルト ``"ja"``
        include_opt_in: True のとき、fuseji の opt-in 認識器（`JP_ADDRESS` /
            `CORPORATE_NUMBER`）も自動で含める。明示的に `recognizers=` を渡した
            場合は本フラグは無視

    Returns:
        登録した Presidio 認識器のリスト（テスト・デバッグ用に返す）

    Example:
        >>> from presidio_analyzer import AnalyzerEngine  # doctest: +SKIP
        >>> from fuseji.integrations.presidio import register_fuseji_recognizers  # doctest: +SKIP
        >>> analyzer = AnalyzerEngine()  # doctest: +SKIP
        >>> register_fuseji_recognizers(analyzer)  # doctest: +SKIP
        >>> results = analyzer.analyze(  # doctest: +SKIP
        ...     text="マイナンバー: 123456789018", language="ja"
        ... )
    """
    if recognizers is None:
        recognizers = list(default_recognizers())
        if include_opt_in:
            recognizers.append(JpAddressRecognizer())
            recognizers.append(CorporateNumberRecognizer())
    registered: list[Any] = []
    for r in recognizers:
        adapter = fuseji_to_presidio_recognizer(r, supported_language=supported_language)
        analyzer.registry.add_recognizer(adapter)
        registered.append(adapter)
    return registered


__all__ = [
    "fuseji_to_presidio_recognizer",
    "register_fuseji_recognizers",
]
