"""FakerStrategy のテスト (#128, `[faker]` extra 必須)."""

from __future__ import annotations

import pytest

# Faker が無い環境ではテスト全体をスキップ
pytest.importorskip("faker")

from fuseji import Masker
from fuseji.faker_strategy import FakerStrategy
from fuseji.types import Entity


def _entity(type_: str, text: str, start: int, end: int, score: float = 0.9) -> Entity:
    return Entity(
        type=type_,
        text=text,
        start=start,
        end=end,
        score=score,
        recognizer="test",
    )


class TestFakerStrategyBasics:
    def test_PERSON_は_Faker_の名前で置換される(self) -> None:
        strategy = FakerStrategy(salt="t")
        entities = [_entity("PERSON", "田中太郎", 0, 4)]
        masked, _ = strategy.mask("田中太郎", entities)
        # 元の surface ではない値に置換される
        assert masked != "田中太郎"
        # Faker (ja_JP) は日本語の名前を生成するので、ASCII オンリーではない
        assert any(ord(c) > 127 for c in masked)

    def test_EMAIL_は_safe_email_で置換される(self) -> None:
        # Faker.safe_email は example.com/.org/.net (RFC 6761) を返す
        strategy = FakerStrategy(salt="t")
        entities = [_entity("EMAIL", "taro@real.example.jp", 0, 21)]
        masked, _ = strategy.mask("taro@real.example.jp", entities)
        assert "real.example.jp" not in masked
        # safe_email の domain (example.com/.org/.net) を含むはず
        assert any(d in masked for d in ("example.com", "example.org", "example.net"))

    def test_JP_PHONE_NUMBER_は_安全な_fictitious_format_で置換(self) -> None:
        strategy = FakerStrategy(salt="t")
        entities = [_entity("JP_PHONE_NUMBER", "090-1234-5678", 0, 13)]
        masked, _ = strategy.mask("090-1234-5678", entities)
        # 安全な fictitious 局番 070-0000 / 080-0000 / 090-0000 を使用
        assert any(masked.startswith(p) for p in ("070-0000", "080-0000", "090-0000"))
        # 元の番号ではない
        assert masked != "090-1234-5678"

    def test_JP_POSTAL_CODE_は_999_局番で置換(self) -> None:
        strategy = FakerStrategy(salt="t")
        entities = [_entity("JP_POSTAL_CODE", "123-4567", 0, 8)]
        masked, _ = strategy.mask("123-4567", entities)
        # 999 局番（実在しない）
        assert masked.startswith("999-")
        assert masked != "123-4567"

    def test_CREDIT_CARD_は_固定マスクで再検出を防ぐ(self) -> None:
        # Faker は Luhn 通過の架空 CC を生成しうるため、固定マスクで再検出回避
        strategy = FakerStrategy(salt="t")
        entities = [_entity("CREDIT_CARD", "4242-4242-4242-4242", 0, 19)]
        masked, _ = strategy.mask("4242-4242-4242-4242", entities)
        assert masked == "<MASKED>"

    def test_MY_NUMBER_は_固定マスク_番号法対応(self) -> None:
        strategy = FakerStrategy(salt="t")
        entities = [_entity("MY_NUMBER", "123456789018", 0, 12)]
        masked, _ = strategy.mask("123456789018", entities)
        assert masked == "<MASKED>"

    def test_CORPORATE_NUMBER_は_固定マスク(self) -> None:
        strategy = FakerStrategy(salt="t")
        entities = [_entity("CORPORATE_NUMBER", "7000012050002", 0, 13)]
        masked, _ = strategy.mask("7000012050002", entities)
        assert masked == "<MASKED>"

    def test_未知の_type_は_TYPE_でマスク(self) -> None:
        strategy = FakerStrategy(salt="t")
        entities = [_entity("CUSTOM_TYPE", "secret", 0, 6)]
        masked, _ = strategy.mask("secret", entities)
        assert masked == "<CUSTOM_TYPE>"

    def test_空_entities_は素通し(self) -> None:
        strategy = FakerStrategy(salt="t")
        masked, mapping = strategy.mask("PII なし", [])
        assert masked == "PII なし"
        assert mapping == {}


class TestDeterminism:
    def test_同一_surface_には同一架空値_default(self) -> None:
        # deterministic=True (default): 同じ surface → 同じ fake
        # mapping の確認は keep_mapping=True 経由で
        strategy = FakerStrategy(salt="t", keep_mapping=True)
        entities = [
            _entity("PERSON", "田中太郎", 0, 4),
            _entity("PERSON", "田中太郎", 10, 14),
        ]
        text = "田中太郎 さん 田中太郎"
        _, mapping = strategy.mask(text, entities)
        # mapping のキー数は 1 (同じ surface に同じ fake)
        assert len(mapping) == 1

    def test_異なる_surface_には異なる架空値(self) -> None:
        strategy = FakerStrategy(salt="t", keep_mapping=True)
        entities = [
            _entity("PERSON", "田中", 0, 2),
            _entity("PERSON", "佐藤", 5, 7),
        ]
        _, mapping = strategy.mask("田中 と 佐藤", entities)
        assert len(mapping) == 2

    def test_デフォルトは_mapping_に_PII_を残さない_security(self) -> None:
        # #139: デフォルト keep_mapping=False で原 PII が mapping に漏れないこと
        strategy = FakerStrategy(salt="t")
        entities = [
            _entity("EMAIL", "taro@example.co.jp", 0, 18),
            _entity("JP_PHONE_NUMBER", "090-1234-5678", 19, 32),
        ]
        text = "taro@example.co.jp、090-1234-5678"
        _, mapping = strategy.mask(text, entities)
        # 原 PII は一切残らない
        assert mapping == {}
        for v in mapping.values():
            assert "taro" not in v
            assert "1234-5678" not in v

    def test_keep_mapping_True_を明示すれば_fake_to_原_PII_を返す(self) -> None:
        strategy = FakerStrategy(salt="t", keep_mapping=True)
        entities = [_entity("EMAIL", "taro@example.co.jp", 0, 18)]
        _, mapping = strategy.mask("taro@example.co.jp", entities)
        # keep_mapping=True なら従来通り mapping に保持
        assert len(mapping) == 1
        assert "taro@example.co.jp" in mapping.values()

    def test_salt_を変えると架空値も変わる(self) -> None:
        e = [_entity("PERSON", "田中", 0, 2)]
        m1, _ = FakerStrategy(salt="salt1").mask("田中", e)
        m2, _ = FakerStrategy(salt="salt2").mask("田中", e)
        # 同じ surface でも salt が違えば異なる fake が出るはず（ハッシュ依存）
        assert m1 != m2

    def test_deterministic_False_は呼び出しごとに変化しうる(self) -> None:
        # 偶然同じ値になる確率はゼロではないが極めて低い
        strategy = FakerStrategy(salt="t", deterministic=False)
        entities = [_entity("PERSON", "田中太郎", 0, 4)]
        results = {strategy.mask("田中太郎", entities)[0] for _ in range(5)}
        # 5 回呼んで複数の異なる値が観測される
        assert len(results) > 1


class TestErrorHandling:
    def test_空_salt_は_InvalidConfigError(self) -> None:
        from fuseji.exceptions import InvalidConfigError

        with pytest.raises(InvalidConfigError, match="salt"):
            FakerStrategy(salt="")


class TestIntegrationWithMasker:
    def test_Masker_と統合してフルパイプラインで動作(self) -> None:
        m = Masker(strategy=FakerStrategy(salt="t"))
        result = m.mask("メールは taro@example.com まで")
        # 元のメールではない値に置換される
        assert "taro@example.com" not in result.text
        # safe domain を含む
        assert any(d in result.text for d in ("example.com", "example.org", "example.net"))
