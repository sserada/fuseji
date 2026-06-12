"""`fuseji.integrations.presidio` のテスト (#147, `[presidio]` extra 必須)."""

from __future__ import annotations

import pytest

pytest.importorskip("presidio_analyzer", reason="presidio-analyzer required for #147 adapter")

from fuseji.integrations.presidio import (
    _TYPE_MAP,
    fuseji_to_presidio_recognizer,
    register_fuseji_recognizers,
)
from fuseji.recognizers.base import default_recognizers
from fuseji.recognizers.corporate_number import CorporateNumberRecognizer
from fuseji.recognizers.email import EmailRecognizer
from fuseji.recognizers.jp_address import JpAddressRecognizer
from fuseji.recognizers.my_number import MyNumberRecognizer


class TestAdapter:
    """fuseji の Recognizer → Presidio EntityRecognizer 変換."""

    def test_email_は_EMAIL_ADDRESS_に_マッピング(self) -> None:
        adapter = fuseji_to_presidio_recognizer(EmailRecognizer())
        # supported_entities は Presidio の標準名と一致
        assert adapter.supported_entities == ["EMAIL_ADDRESS"]
        assert adapter.supported_language == "ja"
        assert "fuseji_" in adapter.name

    def test_my_number_は_JP_MY_NUMBER_に_マッピング(self) -> None:
        adapter = fuseji_to_presidio_recognizer(MyNumberRecognizer())
        assert adapter.supported_entities == ["JP_MY_NUMBER"]

    def test_corporate_number_は_JP_CORPORATE_NUMBER_に_マッピング(self) -> None:
        adapter = fuseji_to_presidio_recognizer(CorporateNumberRecognizer())
        assert adapter.supported_entities == ["JP_CORPORATE_NUMBER"]

    def test_jp_address_は_同名で_マッピング(self) -> None:
        adapter = fuseji_to_presidio_recognizer(JpAddressRecognizer())
        assert adapter.supported_entities == ["JP_ADDRESS"]

    def test_entity_name_を_明示すれば_その名前で_登録(self) -> None:
        adapter = fuseji_to_presidio_recognizer(
            MyNumberRecognizer(), entity_name="CUSTOM_MY_NUMBER"
        )
        assert adapter.supported_entities == ["CUSTOM_MY_NUMBER"]

    def test_supported_language_を_明示すれば_その言語で_登録(self) -> None:
        adapter = fuseji_to_presidio_recognizer(EmailRecognizer(), supported_language="en")
        assert adapter.supported_language == "en"


class TestAdapterAnalyze:
    """アダプタの analyze() が fuseji Entity を Presidio RecognizerResult に変換."""

    def test_email_検出が_RecognizerResult_として_返る(self) -> None:
        adapter = fuseji_to_presidio_recognizer(EmailRecognizer())
        # Presidio の analyze は entities=[] で空 list を全 type 許容と仕様で扱う
        text = "メール: taro@example.com です"
        results = adapter.analyze(text=text, entities=[], nlp_artifacts=None)
        assert len(results) == 1
        r = results[0]
        assert r.entity_type == "EMAIL_ADDRESS"
        # オフセットは fuseji Entity と同じ（変換は加工しない）
        assert text[r.start : r.end] == "taro@example.com"
        assert r.score == 1.0

    def test_my_number_検出が_JP_MY_NUMBER_として_返る(self) -> None:
        adapter = fuseji_to_presidio_recognizer(MyNumberRecognizer())
        results = adapter.analyze(text="番号: 123456789018 です", entities=[], nlp_artifacts=None)
        assert len(results) == 1
        assert results[0].entity_type == "JP_MY_NUMBER"

    def test_entities_フィルタが_かかる_対象外なら_空(self) -> None:
        # Presidio から「EMAIL_ADDRESS だけ」と要求されたとき、MyNumber adapter は空
        adapter = fuseji_to_presidio_recognizer(MyNumberRecognizer())
        results = adapter.analyze(
            text="123456789018", entities=["EMAIL_ADDRESS"], nlp_artifacts=None
        )
        assert results == []

    def test_entities_フィルタに_自分の_type_が_あれば_検出(self) -> None:
        adapter = fuseji_to_presidio_recognizer(MyNumberRecognizer())
        results = adapter.analyze(
            text="123456789018", entities=["JP_MY_NUMBER"], nlp_artifacts=None
        )
        assert len(results) == 1

    def test_nlp_artifacts_が_None_でも_動作(self) -> None:
        # fuseji は internally normalize で全半角扱うため Presidio の nlp_artifacts に依存しない
        adapter = fuseji_to_presidio_recognizer(EmailRecognizer())
        results = adapter.analyze(text="taro@example.com", entities=[], nlp_artifacts=None)
        assert len(results) == 1


class TestRegisterFusejiRecognizers:
    """analyzer.registry に fuseji 認識器を一括登録するヘルパ."""

    def _fake_analyzer(self) -> object:
        # AnalyzerEngine は NLP engine を必要とするため、registry.add_recognizer のみ
        # 検証する軽量フェイクで十分。
        class _FakeRegistry:
            def __init__(self) -> None:
                self.recognizers: list[object] = []

            def add_recognizer(self, recognizer: object) -> None:
                self.recognizers.append(recognizer)

        class _FakeAnalyzer:
            def __init__(self) -> None:
                self.registry = _FakeRegistry()

        return _FakeAnalyzer()

    def test_デフォルトで_v01_認識器_全件_と_opt_in_を_登録(self) -> None:
        analyzer = self._fake_analyzer()
        registered = register_fuseji_recognizers(analyzer)  # type: ignore[arg-type]
        # v0.1 default (5 / 6 件、ginza 未インストールなら 5)+ opt-in 2 件
        defaults = list(default_recognizers())
        expected_count = len(defaults) + 2  # +JpAddress +CorporateNumber
        assert len(registered) == expected_count
        # 主要 type が網羅されている
        registered_types = {next(iter(a.supported_entities)) for a in registered}
        assert "EMAIL_ADDRESS" in registered_types
        assert "JP_MY_NUMBER" in registered_types
        assert "JP_PHONE_NUMBER" in registered_types
        assert "JP_POSTAL_CODE" in registered_types
        assert "CREDIT_CARD" in registered_types
        assert "JP_ADDRESS" in registered_types
        assert "JP_CORPORATE_NUMBER" in registered_types

    def test_include_opt_in_False_なら_v01_デフォルトのみ(self) -> None:
        analyzer = self._fake_analyzer()
        registered = register_fuseji_recognizers(analyzer, include_opt_in=False)  # type: ignore[arg-type]
        registered_types = {next(iter(a.supported_entities)) for a in registered}
        assert "JP_ADDRESS" not in registered_types
        assert "JP_CORPORATE_NUMBER" not in registered_types
        # default は残る
        assert "EMAIL_ADDRESS" in registered_types

    def test_明示的に_recognizers_を_渡せる(self) -> None:
        analyzer = self._fake_analyzer()
        registered = register_fuseji_recognizers(
            analyzer,  # type: ignore[arg-type]
            recognizers=[MyNumberRecognizer()],
        )
        assert len(registered) == 1
        assert registered[0].supported_entities == ["JP_MY_NUMBER"]

    def test_supported_language_を_明示できる(self) -> None:
        analyzer = self._fake_analyzer()
        registered = register_fuseji_recognizers(
            analyzer,  # type: ignore[arg-type]
            recognizers=[MyNumberRecognizer()],
            supported_language="en",
        )
        assert registered[0].supported_language == "en"


class TestTypeMap:
    """エンティティ名マッピングの網羅性."""

    def test_全_default_recognizer_type_が_マッピングされている(self) -> None:
        for r in default_recognizers():
            assert r.entity_type in _TYPE_MAP, f"{r.entity_type} が _TYPE_MAP に未登録"

    def test_opt_in_認識器も_マッピングされている(self) -> None:
        assert JpAddressRecognizer().entity_type in _TYPE_MAP
        assert CorporateNumberRecognizer().entity_type in _TYPE_MAP

    def test_日本語専用_type_は_JP_接頭辞(self) -> None:
        # 名前空間衝突を避けるため Presidio に存在しない type は JP_* で登録
        assert _TYPE_MAP["MY_NUMBER"].startswith("JP_")
        assert _TYPE_MAP["CORPORATE_NUMBER"].startswith("JP_")
