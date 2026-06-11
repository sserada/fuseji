"""vault.py のテスト."""

from __future__ import annotations

from fuseji.vault import InMemoryVault


class TestAssign:
    def test_新規_surface_に_placeholder_を割当(self) -> None:
        v = InMemoryVault()
        assert v.assign("PERSON", "田中") == "<PERSON_1>"

    def test_同一_type_surface_は同一_placeholder(self) -> None:
        v = InMemoryVault()
        first = v.assign("PERSON", "田中")
        second = v.assign("PERSON", "田中")
        assert first == second == "<PERSON_1>"

    def test_異なる_surface_は別番号(self) -> None:
        v = InMemoryVault()
        assert v.assign("PERSON", "田中") == "<PERSON_1>"
        assert v.assign("PERSON", "佐藤") == "<PERSON_2>"

    def test_type_ごとに番号系列が独立(self) -> None:
        v = InMemoryVault()
        assert v.assign("PERSON", "田中") == "<PERSON_1>"
        assert v.assign("EMAIL", "x@y.z") == "<EMAIL_1>"
        assert v.assign("PERSON", "佐藤") == "<PERSON_2>"
        assert v.assign("EMAIL", "a@b.c") == "<EMAIL_2>"

    def test_同じ_surface_でも_type_が違えば別_placeholder(self) -> None:
        v = InMemoryVault()
        p1 = v.assign("PERSON", "山田")
        p2 = v.assign("COMPANY", "山田")
        assert p1 == "<PERSON_1>"
        assert p2 == "<COMPANY_1>"
        assert p1 != p2


class TestExcludedTypes:
    def test_デフォルトは_MY_NUMBER_と_CREDIT_CARD_を除外(self) -> None:
        # v0.2: 番号法対応 (MY_NUMBER) + PCI DSS 整合 (CREDIT_CARD) で両方除外
        v = InMemoryVault()
        assert v.excluded_types == frozenset({"MY_NUMBER", "CREDIT_CARD"})

    def test_MY_NUMBER_は_None_を返す(self) -> None:
        v = InMemoryVault()
        assert v.assign("MY_NUMBER", "123456789012") is None

    def test_CREDIT_CARD_は_None_を返す(self) -> None:
        # PCI DSS 整合: PAN を mapping に残さない（#84）
        v = InMemoryVault()
        assert v.assign("CREDIT_CARD", "4242424242424242") is None

    def test_除外_type_は対応表に残らない(self) -> None:
        v = InMemoryVault()
        v.assign("MY_NUMBER", "123456789012")
        v.assign("CREDIT_CARD", "4242424242424242")
        assert v.restore("<MY_NUMBER_1>") == "<MY_NUMBER_1>"
        assert v.restore("<CREDIT_CARD_1>") == "<CREDIT_CARD_1>"
        assert v.get("<MY_NUMBER_1>") is None
        assert v.get("<CREDIT_CARD_1>") is None

    def test_カスタム除外集合(self) -> None:
        v = InMemoryVault(excluded_types=["EMAIL", "CREDIT_CARD"])
        assert v.assign("EMAIL", "x@y.z") is None
        assert v.assign("CREDIT_CARD", "4111111111111111") is None
        # MY_NUMBER はもう除外されない（明示的に上書きされた）
        assert v.assign("MY_NUMBER", "123456789012") == "<MY_NUMBER_1>"

    def test_空集合の除外指定_はデフォルトを無効化(self) -> None:
        v = InMemoryVault(excluded_types=[])
        assert v.excluded_types == frozenset()
        assert v.assign("MY_NUMBER", "123456789012") == "<MY_NUMBER_1>"


class TestGet:
    def test_登録済み_placeholder(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.get("<PERSON_1>") == "田中"

    def test_未登録は_None(self) -> None:
        v = InMemoryVault()
        assert v.get("<UNKNOWN_1>") is None


class TestRestore:
    def test_単一_placeholder_を復元(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.restore("<PERSON_1>さん、こんにちは") == "田中さん、こんにちは"

    def test_複数_placeholder_を復元(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        v.assign("PERSON", "佐藤")
        assert v.restore("<PERSON_1>と<PERSON_2>") == "田中と佐藤"

    def test_未登録_placeholder_は素通し(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.restore("<PERSON_1>と<UNKNOWN_1>") == "田中と<UNKNOWN_1>"

    def test_excluded_type_の番号なし_placeholder_は素通し(self) -> None:
        # MY_NUMBER は assign で None を返し対応表に残らない。
        # excluded type は <TYPE>（番号なし）形式でマスクされるが、placeholder
        # 形式 <TYPE_N> にはマッチしないので restore でも素通しになる。
        v = InMemoryVault()
        assert v.restore("マイナンバーは <MY_NUMBER>") == "マイナンバーは <MY_NUMBER>"

    def test_別_vault_由来の_placeholder_は素通し(self) -> None:
        # vault1 に登録した placeholder を vault2 で復元しようとしても
        # silent corruption しない。
        vault1 = InMemoryVault()
        vault1.assign("PERSON", "田中")
        vault2 = InMemoryVault()
        # vault2 には田中の登録がないので、<PERSON_1> はそのまま残る
        assert vault2.restore("<PERSON_1>さん") == "<PERSON_1>さん"

    def test_テキストに偶然含まれる_placeholder_形式は素通し(self) -> None:
        # ユーザーテキストに偶然 <PERSON_999> という文字列が含まれていても、
        # vault に未登録なので素通しになる（silent corruption ゼロ確認）。
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        text = "コード内のサンプル <PERSON_999> と実データ <PERSON_1>"
        assert v.restore(text) == "コード内のサンプル <PERSON_999> と実データ 田中"

    def test_番号が二桁以上でも誤置換しない(self) -> None:
        v = InMemoryVault()
        for i in range(1, 12):  # PERSON_1 ... PERSON_11
            v.assign("PERSON", f"name_{i}")
        # PERSON_11 の置換が PERSON_1 + "1" として誤マッチしないこと
        restored = v.restore("<PERSON_11>")
        assert restored == "name_11"

    def test_placeholder_を含まないテキストは変更なし(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.restore("変更なしのテキスト") == "変更なしのテキスト"

    def test_空のバウルトは何も置換しない(self) -> None:
        v = InMemoryVault()
        assert v.restore("<PERSON_1>") == "<PERSON_1>"


class TestRepr:
    def test_空の_repr(self) -> None:
        v = InMemoryVault()
        r = repr(v)
        assert "InMemoryVault" in r
        assert "size=0" in r
        assert "'MY_NUMBER'" in r  # default excluded

    def test_assign_後の_repr_は_size_を反映(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "山田")
        v.assign("PERSON", "佐藤")
        r = repr(v)
        assert "size=2" in r

    def test_カスタム_excluded_の_repr(self) -> None:
        v = InMemoryVault(excluded_types=["EMAIL", "CREDIT_CARD"])
        r = repr(v)
        assert "'CREDIT_CARD'" in r
        assert "'EMAIL'" in r


class TestSize:
    def test_初期は_0(self) -> None:
        v = InMemoryVault()
        assert v.size == 0

    def test_assign_でカウントが増える(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        assert v.size == 1
        v.assign("PERSON", "佐藤")
        assert v.size == 2
        v.assign("EMAIL", "x@y.z")
        assert v.size == 3

    def test_同一_surface_の重複_assign_は増えない(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        v.assign("PERSON", "田中")
        v.assign("PERSON", "田中")
        assert v.size == 1

    def test_excluded_type_の_assign_は増えない(self) -> None:
        v = InMemoryVault()
        v.assign("MY_NUMBER", "123456789012")  # None を返す
        assert v.size == 0

    def test_clear_で_0_に戻る(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "田中")
        v.assign("EMAIL", "x@y.z")
        assert v.size == 2
        v.clear()
        assert v.size == 0


class TestClear:
    def test_clear_は全てのマッピングを破棄(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "山田")
        v.assign("EMAIL", "a@b.com")
        v.clear()
        assert v.get("<PERSON_1>") is None
        assert v.get("<EMAIL_1>") is None
        assert v.restore("<PERSON_1>") == "<PERSON_1>"  # 素通し

    def test_clear_後はカウンタも_1_から再開(self) -> None:
        v = InMemoryVault()
        v.assign("PERSON", "山田")
        v.assign("PERSON", "佐藤")
        assert v.assign("PERSON", "田中") == "<PERSON_3>"
        v.clear()
        assert v.assign("PERSON", "鈴木") == "<PERSON_1>"

    def test_clear_は_excluded_types_設定を保持(self) -> None:
        v = InMemoryVault(excluded_types=["EMAIL"])
        v.assign("PERSON", "山田")
        v.clear()
        # excluded_types は維持されたまま
        assert "EMAIL" in v.excluded_types
        assert v.assign("EMAIL", "x@y.z") is None


class TestThreadSafety:
    def test_並行_assign_でも採番衝突しない(self) -> None:
        """複数スレッドで同じ surface を assign しても placeholder は 1 つに収束."""
        import threading

        v = InMemoryVault()
        results: list[str | None] = []
        results_lock = threading.Lock()

        def worker() -> None:
            ph = v.assign("PERSON", "田中")
            with results_lock:
                results.append(ph)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 全スレッドが同じ placeholder を取得
        assert len(set(results)) == 1
        # カウンタは 1 つだけ進んだ
        assert v.assign("PERSON", "別人") == "<PERSON_2>"

    def test_異なる_surface_の並行_assign_で番号が重複しない(self) -> None:
        """異なる surface を並行 assign しても番号がユニーク."""
        import threading

        v = InMemoryVault()
        surfaces = [f"name_{i}" for i in range(100)]
        results: dict[str, str | None] = {}
        results_lock = threading.Lock()

        def worker(surface: str) -> None:
            ph = v.assign("PERSON", surface)
            with results_lock:
                results[surface] = ph

        threads = [threading.Thread(target=worker, args=(s,)) for s in surfaces]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 全 surface に placeholder が割り当てられ、すべてユニーク
        assert len(results) == 100
        placeholders = list(results.values())
        assert len(set(placeholders)) == 100


class TestVaultProtocol:
    """InMemoryVault が Vault プロトコルを満たすことの確認."""

    def test_InMemoryVault_は_Vault_として扱える(self) -> None:
        from fuseji.vault import Vault

        v: Vault = InMemoryVault()
        v.assign("PERSON", "山田")
        assert v.get("<PERSON_1>") == "山田"
        assert v.restore("<PERSON_1>") == "山田"


class TestMaxSize:
    """max_size による FIFO eviction の挙動 (#86)."""

    def test_max_size_未指定なら無制限(self) -> None:
        v = InMemoryVault()
        for i in range(50):
            v.assign("PERSON", f"surface{i}")
        assert v.size == 50

    def test_max_size_到達後は_FIFO_で最古を退避(self) -> None:
        v = InMemoryVault(max_size=3)
        v.assign("PERSON", "A")  # <PERSON_1>
        v.assign("PERSON", "B")  # <PERSON_2>
        v.assign("PERSON", "C")  # <PERSON_3>
        assert v.size == 3
        v.assign("PERSON", "D")  # <PERSON_4>, A が退避される
        assert v.size == 3
        # A は退避されたので restore できない
        assert v.get("<PERSON_1>") is None
        # B/C/D は残る
        assert v.get("<PERSON_2>") == "B"
        assert v.get("<PERSON_3>") == "C"
        assert v.get("<PERSON_4>") == "D"

    def test_退避後も新規番号は単調増加(self) -> None:
        # FIFO で退避した番号は再利用しない（restore 時の衝突防止）
        v = InMemoryVault(max_size=2)
        v.assign("PERSON", "A")  # <PERSON_1>
        v.assign("PERSON", "B")  # <PERSON_2>
        v.assign("PERSON", "C")  # <PERSON_3> (A 退避)
        v.assign("PERSON", "D")  # <PERSON_4> (B 退避)
        # A/B の placeholder は退避済み、新規は 3 以上
        assert v.get("<PERSON_3>") == "C"
        assert v.get("<PERSON_4>") == "D"

    def test_既存_surface_への_assign_は退避を発火しない(self) -> None:
        v = InMemoryVault(max_size=2)
        v.assign("PERSON", "A")
        v.assign("PERSON", "B")
        # 既存 surface の再 assign は新規エントリを作らない
        v.assign("PERSON", "A")  # cache hit、新規挿入しない
        assert v.size == 2
        assert v.get("<PERSON_1>") == "A"
        assert v.get("<PERSON_2>") == "B"

    def test_max_size_0_以下は_InvalidConfigError(self) -> None:
        import pytest

        from fuseji.exceptions import InvalidConfigError

        with pytest.raises(InvalidConfigError):
            InMemoryVault(max_size=0)
        with pytest.raises(InvalidConfigError):
            InMemoryVault(max_size=-1)

    def test_clear_後も_max_size_が維持される(self) -> None:
        v = InMemoryVault(max_size=2)
        v.assign("PERSON", "A")
        v.assign("PERSON", "B")
        v.clear()
        assert v.size == 0
        # clear 後も max_size は維持
        v.assign("PERSON", "C")
        v.assign("PERSON", "D")
        v.assign("PERSON", "E")
        assert v.size == 2  # max_size 上限が引き続き効く
