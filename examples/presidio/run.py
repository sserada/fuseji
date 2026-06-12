"""Presidio から fuseji 認識器を呼ぶサンプル (#147).

実行前提:
    pip install 'fuseji[presidio]'
    python -m spacy download ja_core_news_sm
"""

from __future__ import annotations

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from fuseji.integrations.presidio import register_fuseji_recognizers


def main() -> None:
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "ja", "model_name": "ja_core_news_sm"}],
    }
    nlp_engine = NlpEngineProvider(nlp_engine_configuration=nlp_config).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["ja"])

    register_fuseji_recognizers(analyzer)

    text = "マイナンバー: 123456789018 電話 090-1234-5678 メール: taro@example.com"
    results = analyzer.analyze(text=text, language="ja")
    for r in sorted(results, key=lambda x: x.start):
        print(f"{r.entity_type} (score={r.score}) at {r.start}-{r.end}: {text[r.start : r.end]}")


if __name__ == "__main__":
    main()
