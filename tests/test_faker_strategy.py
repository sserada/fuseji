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


class TestSaltDefaultRandomized:
    """#145: デフォルト salt が固定ではなく per-instance random であること."""

    def test_デフォルト_salt_は_インスタンス毎に_異なる(self) -> None:
        s1 = FakerStrategy()
        s2 = FakerStrategy()
        assert s1.salt != s2.salt

    def test_デフォルト_salt_は_長く_十分なエントロピー(self) -> None:
        s = FakerStrategy()
        # secrets.token_hex(32) → 64 文字 hex (256bit)
        assert len(s.salt) == 64
        assert all(c in "0123456789abcdef" for c in s.salt)

    def test_デフォルト_salt_は_ソース固定の旧定数とは別物(self) -> None:
        # v0.3 のデフォルト salt 文字列が偶然返ってこないこと
        legacy_default = "fuseji-default-salt-please-override"
        for _ in range(10):
            assert FakerStrategy().salt != legacy_default

    def test_明示_salt_は_従来通り_cross_instance_等価性を保つ(self) -> None:
        # マルチプロセス間の決定性が必要なときは明示的に渡す
        s1 = FakerStrategy(salt="shared-secret")
        s2 = FakerStrategy(salt="shared-secret")
        v1 = s1._fake_for("PERSON", "田中")
        v2 = s2._fake_for("PERSON", "田中")
        assert v1 == v2

    def test_デフォルト_salt_では_別インスタンス間の_fake_が_異なる(self) -> None:
        # ランダム salt → 別インスタンスの同じ surface は別 fake
        s1 = FakerStrategy()
        s2 = FakerStrategy()
        # 何度か試して衝突しないことを確認 (確率的だが 256bit salt で実質ゼロ)
        v1 = s1._fake_for("EMAIL", "taro@example.com")
        v2 = s2._fake_for("EMAIL", "taro@example.com")
        assert v1 != v2

    def test_repr_に_salt_が_露出しない(self) -> None:
        # ログ漏洩経路で salt を保護 (#145)
        s = FakerStrategy(salt="super-secret-key")
        assert "super-secret-key" not in repr(s)
        assert "<redacted>" in repr(s)


class TestCacheBounded:
    """#177: _faker_cache の max_cache_size LRU 削除."""

    def test_デフォルト_max_cache_size_は_8192(self) -> None:
        s = FakerStrategy()
        assert s.max_cache_size == 8192

    def test_上限超過で_最古エントリが_LRU_で_捨てられる(self) -> None:
        s = FakerStrategy(max_cache_size=3)
        # 3 件まで充填
        s._fake_for("PERSON", "alpha")
        s._fake_for("PERSON", "beta")
        s._fake_for("PERSON", "gamma")
        assert len(s._faker_cache) == 3
        # 4 件目投入 → 最古 (alpha) が捨てられる
        s._fake_for("PERSON", "delta")
        assert len(s._faker_cache) == 3
        assert "PERSON:alpha" not in s._faker_cache
        assert "PERSON:delta" in s._faker_cache

    def test_hit_すると_LRU_順で_末尾に_動く(self) -> None:
        # alpha → beta → gamma の順に投入後、alpha を hit させると alpha が
        # 末尾に動き、次の追加 (delta) で beta が削除される (alpha は生存)。
        s = FakerStrategy(max_cache_size=3)
        s._fake_for("PERSON", "alpha")
        s._fake_for("PERSON", "beta")
        s._fake_for("PERSON", "gamma")
        # alpha を再 hit
        s._fake_for("PERSON", "alpha")
        # delta 追加 → beta (最古) が削除される
        s._fake_for("PERSON", "delta")
        assert "PERSON:beta" not in s._faker_cache
        assert "PERSON:alpha" in s._faker_cache
        assert "PERSON:gamma" in s._faker_cache
        assert "PERSON:delta" in s._faker_cache

    def test_max_cache_size_0_は_無制限(self) -> None:
        s = FakerStrategy(max_cache_size=0)
        for i in range(100):
            s._fake_for("PERSON", f"surface_{i}")
        # 100 件すべて生存
        assert len(s._faker_cache) == 100

    def test_deterministic_False_でも_例外なし(self) -> None:
        # deterministic=False では cache を経由しないため max_cache_size の影響なし
        s = FakerStrategy(deterministic=False, max_cache_size=3)
        for i in range(10):
            s._fake_for("PERSON", f"surface_{i}")
        # cache に追加されない
        assert len(s._faker_cache) == 0


class TestFakerInstanceReuse:
    """#142 — Faker インスタンスは strategy あたり 1 回だけ構築されること."""

    def test_strategy_あたり_Faker_インスタンスは_スレッド毎に_1_個(self) -> None:
        # #210: threading.local で per-thread に 1 個保持。
        # 100 unique surface を同一スレッドで流しても current thread の Faker は 1 個
        strategy = FakerStrategy(salt="t")
        for i in range(100):
            strategy._fake_for("PERSON", f"surface_{i}")
        # current thread の faker が初期化済み
        assert getattr(strategy._faker_local, "fake", None) is not None

    def test_インスタンス再利用しても決定性が保たれる(self) -> None:
        # 同じ surface に同じ fake が返ること（seed_instance による seed 切替が機能）
        strategy = FakerStrategy(salt="t")
        # 別 surface を間に挟んでも同じ surface には同じ fake が返る
        v1 = strategy._fake_for("PERSON", "田中太郎")
        _ = strategy._fake_for("PERSON", "佐藤花子")
        v2 = strategy._fake_for("PERSON", "田中太郎")
        # cache hit 経由でも同じ
        assert v1 == v2

    def test_インスタンス再利用しても異なる_surface_には異なる_fake(self) -> None:
        strategy = FakerStrategy(salt="t")
        # cache を経由しない一意な surface ペア
        v1 = strategy._fake_for("PERSON", "alpha")
        v2 = strategy._fake_for("PERSON", "beta")
        assert v1 != v2

    def test_cross_instance_determinism_は維持される(self) -> None:
        # 同じ salt の独立 strategy が同じ surface に同じ fake を返す
        # （旧実装の仕様を保持）
        s1 = FakerStrategy(salt="t")
        s2 = FakerStrategy(salt="t")
        v1 = s1._fake_for("PERSON", "user1")
        v2 = s2._fake_for("PERSON", "user1")
        assert v1 == v2


class TestThreadSafety:
    """#210 — 並行呼び出しでの決定性 / レース回避."""

    def test_並行下でも_同一_surface_は_同一_fake_に_解決される(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        strategy = FakerStrategy(deterministic=True, salt="thread-test")
        surfaces = [f"user{i}" for i in range(50)] * 8  # 50 unique × 8 = 400 calls

        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(lambda s: strategy._fake_for("PERSON", s), surfaces))

        # 同一 surface → 同一 fake であるべき
        groups: dict[str, set[str]] = {}
        for s, r in zip(surfaces, results, strict=False):
            groups.setdefault(s, set()).add(r)
        races = {s: vs for s, vs in groups.items() if len(vs) > 1}
        assert races == {}, f"並行下で決定性が破綻: {races}"

    def test_並行下でも_異なる_surface_は_異なる_fake(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        strategy = FakerStrategy(deterministic=True, salt="thread-test-2")
        # 100 unique surfaces を 8 並列で 1 回ずつ
        surfaces = [f"surface_{i}" for i in range(100)]
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(lambda s: strategy._fake_for("PERSON", s), surfaces))
        # 100 unique surface → fake もほぼ unique (Faker name 集合は十分大きいので衝突は稀)
        assert len(set(results)) >= len(surfaces) * 0.9


class TestIntegrationWithMasker:
    def test_Masker_と統合してフルパイプラインで動作(self) -> None:
        m = Masker(strategy=FakerStrategy(salt="t"))
        result = m.mask("メールは taro@example.com まで")
        # 元のメールではない値に置換される
        assert "taro@example.com" not in result.text
        # safe domain を含む
        assert any(d in result.text for d in ("example.com", "example.org", "example.net"))
