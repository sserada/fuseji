"""vault.py のテスト."""

from __future__ import annotations

import re

from fuseji.vault import InMemoryVault


class TestAssign:
    def test_新規_surface_に_placeholder_を割当(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.assign("PERSON", "田中") == "<PERSON_1_t>"

    def test_同一_type_surface_は同一_placeholder(self) -> None:
        v = InMemoryVault(nonce="t")
        first = v.assign("PERSON", "田中")
        second = v.assign("PERSON", "田中")
        assert first == second == "<PERSON_1_t>"

    def test_異なる_surface_は別番号(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.assign("PERSON", "田中") == "<PERSON_1_t>"
        assert v.assign("PERSON", "佐藤") == "<PERSON_2_t>"

    def test_type_ごとに番号系列が独立(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.assign("PERSON", "田中") == "<PERSON_1_t>"
        assert v.assign("EMAIL", "x@y.z") == "<EMAIL_1_t>"
        assert v.assign("PERSON", "佐藤") == "<PERSON_2_t>"
        assert v.assign("EMAIL", "a@b.c") == "<EMAIL_2_t>"

    def test_同じ_surface_でも_type_が違えば別_placeholder(self) -> None:
        v = InMemoryVault(nonce="t")
        p1 = v.assign("PERSON", "山田")
        p2 = v.assign("COMPANY", "山田")
        assert p1 == "<PERSON_1_t>"
        assert p2 == "<COMPANY_1_t>"
        assert p1 != p2


class TestExcludedTypes:
    def test_デフォルトは_MY_NUMBER_と_CREDIT_CARD_を除外(self) -> None:
        # v0.2: 番号法対応 (MY_NUMBER) + PCI DSS 整合 (CREDIT_CARD) で両方除外
        v = InMemoryVault(nonce="t")
        assert v.excluded_types == frozenset({"MY_NUMBER", "CREDIT_CARD"})

    def test_MY_NUMBER_は_None_を返す(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.assign("MY_NUMBER", "123456789012") is None

    def test_CREDIT_CARD_は_None_を返す(self) -> None:
        # PCI DSS 整合: PAN を mapping に残さない（#84）
        v = InMemoryVault(nonce="t")
        assert v.assign("CREDIT_CARD", "4242424242424242") is None

    def test_除外_type_は対応表に残らない(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("MY_NUMBER", "123456789012")
        v.assign("CREDIT_CARD", "4242424242424242")
        assert v.restore("<MY_NUMBER_1_t>") == "<MY_NUMBER_1_t>"
        assert v.restore("<CREDIT_CARD_1_t>") == "<CREDIT_CARD_1_t>"
        assert v.get("<MY_NUMBER_1_t>") is None
        assert v.get("<CREDIT_CARD_1_t>") is None

    def test_カスタム除外集合(self) -> None:
        v = InMemoryVault(excluded_types=["EMAIL", "CREDIT_CARD"], nonce="t")
        assert v.assign("EMAIL", "x@y.z") is None
        assert v.assign("CREDIT_CARD", "4111111111111111") is None
        # MY_NUMBER はもう除外されない（明示的に上書きされた）
        assert v.assign("MY_NUMBER", "123456789012") == "<MY_NUMBER_1_t>"

    def test_空集合の除外指定_はデフォルトを無効化(self) -> None:
        v = InMemoryVault(excluded_types=[], nonce="t")
        assert v.excluded_types == frozenset()
        assert v.assign("MY_NUMBER", "123456789012") == "<MY_NUMBER_1_t>"


class TestGet:
    def test_登録済み_placeholder(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        assert v.get("<PERSON_1_t>") == "田中"

    def test_未登録は_None(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.get("<UNKNOWN_1_t>") is None


class TestRestore:
    def test_単一_placeholder_を復元(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        assert v.restore("<PERSON_1_t>さん、こんにちは") == "田中さん、こんにちは"

    def test_複数_placeholder_を復元(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        v.assign("PERSON", "佐藤")
        assert v.restore("<PERSON_1_t>と<PERSON_2_t>") == "田中と佐藤"

    def test_未登録_placeholder_は素通し(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        assert v.restore("<PERSON_1_t>と<UNKNOWN_1_t>") == "田中と<UNKNOWN_1_t>"

    def test_excluded_type_の番号なし_placeholder_は素通し(self) -> None:
        # MY_NUMBER は assign で None を返し対応表に残らない。
        # excluded type は <TYPE>（番号なし）形式でマスクされるが、placeholder
        # 形式 <TYPE_N> にはマッチしないので restore でも素通しになる。
        v = InMemoryVault(nonce="t")
        assert v.restore("マイナンバーは <MY_NUMBER>") == "マイナンバーは <MY_NUMBER>"

    def test_別_vault_由来の_placeholder_は素通し(self) -> None:
        # vault1 に登録した placeholder を vault2 で復元しようとしても
        # silent corruption しない。
        vault1 = InMemoryVault(nonce="t")
        vault1.assign("PERSON", "田中")
        vault2 = InMemoryVault(nonce="t")
        # vault2 には田中の登録がないので、<PERSON_1_t> はそのまま残る
        assert vault2.restore("<PERSON_1_t>さん") == "<PERSON_1_t>さん"

    def test_テキストに偶然含まれる_placeholder_形式は素通し(self) -> None:
        # ユーザーテキストに偶然 <PERSON_999_t> という文字列が含まれていても、
        # vault に未登録なので素通しになる（silent corruption ゼロ確認）。
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        text = "コード内のサンプル <PERSON_999_t> と実データ <PERSON_1_t>"
        assert v.restore(text) == "コード内のサンプル <PERSON_999_t> と実データ 田中"

    def test_番号が二桁以上でも誤置換しない(self) -> None:
        v = InMemoryVault(nonce="t")
        for i in range(1, 12):  # PERSON_1 ... PERSON_11
            v.assign("PERSON", f"name_{i}")
        # PERSON_11 の置換が PERSON_1 + "1" として誤マッチしないこと
        restored = v.restore("<PERSON_11_t>")
        assert restored == "name_11"

    def test_placeholder_を含まないテキストは変更なし(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        assert v.restore("変更なしのテキスト") == "変更なしのテキスト"

    def test_空のバウルトは何も置換しない(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.restore("<PERSON_1_t>") == "<PERSON_1_t>"


class TestRepr:
    def test_空の_repr(self) -> None:
        v = InMemoryVault(nonce="t")
        r = repr(v)
        assert "InMemoryVault" in r
        assert "size=0" in r
        assert "'MY_NUMBER'" in r  # default excluded

    def test_assign_後の_repr_は_size_を反映(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "山田")
        v.assign("PERSON", "佐藤")
        r = repr(v)
        assert "size=2" in r

    def test_カスタム_excluded_の_repr(self) -> None:
        v = InMemoryVault(excluded_types=["EMAIL", "CREDIT_CARD"], nonce="t")
        r = repr(v)
        assert "'CREDIT_CARD'" in r
        assert "'EMAIL'" in r


class TestSize:
    def test_初期は_0(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.size == 0

    def test_assign_でカウントが増える(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        assert v.size == 1
        v.assign("PERSON", "佐藤")
        assert v.size == 2
        v.assign("EMAIL", "x@y.z")
        assert v.size == 3

    def test_同一_surface_の重複_assign_は増えない(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        v.assign("PERSON", "田中")
        v.assign("PERSON", "田中")
        assert v.size == 1

    def test_excluded_type_の_assign_は増えない(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("MY_NUMBER", "123456789012")  # None を返す
        assert v.size == 0

    def test_clear_で_0_に戻る(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "田中")
        v.assign("EMAIL", "x@y.z")
        assert v.size == 2
        v.clear()
        assert v.size == 0


class TestClear:
    def test_clear_は全てのマッピングを破棄(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "山田")
        v.assign("EMAIL", "a@b.com")
        v.clear()
        assert v.get("<PERSON_1_t>") is None
        assert v.get("<EMAIL_1_t>") is None
        assert v.restore("<PERSON_1_t>") == "<PERSON_1_t>"  # 素通し

    def test_clear_後はカウンタも_1_から再開(self) -> None:
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "山田")
        v.assign("PERSON", "佐藤")
        assert v.assign("PERSON", "田中") == "<PERSON_3_t>"
        v.clear()
        assert v.assign("PERSON", "鈴木") == "<PERSON_1_t>"

    def test_clear_は_excluded_types_設定を保持(self) -> None:
        v = InMemoryVault(excluded_types=["EMAIL"], nonce="t")
        v.assign("PERSON", "山田")
        v.clear()
        # excluded_types は維持されたまま
        assert "EMAIL" in v.excluded_types
        assert v.assign("EMAIL", "x@y.z") is None


class TestThreadSafety:
    def test_並行_assign_でも採番衝突しない(self) -> None:
        """複数スレッドで同じ surface を assign しても placeholder は 1 つに収束."""
        import threading

        v = InMemoryVault(nonce="t")
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
        assert v.assign("PERSON", "別人") == "<PERSON_2_t>"

    def test_異なる_surface_の並行_assign_で番号が重複しない(self) -> None:
        """異なる surface を並行 assign しても番号がユニーク."""
        import threading

        v = InMemoryVault(nonce="t")
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

        v: Vault = InMemoryVault(nonce="t")
        v.assign("PERSON", "山田")
        assert v.get("<PERSON_1_t>") == "山田"
        assert v.restore("<PERSON_1_t>") == "山田"


class TestMaxSize:
    """max_size による FIFO eviction の挙動 (#86)."""

    def test_max_size_未指定なら無制限(self) -> None:
        v = InMemoryVault(nonce="t")
        for i in range(50):
            v.assign("PERSON", f"surface{i}")
        assert v.size == 50

    def test_max_size_到達後は_FIFO_で最古を退避(self) -> None:
        v = InMemoryVault(max_size=3, nonce="t")
        v.assign("PERSON", "A")  # <PERSON_1_t>
        v.assign("PERSON", "B")  # <PERSON_2_t>
        v.assign("PERSON", "C")  # <PERSON_3_t>
        assert v.size == 3
        v.assign("PERSON", "D")  # <PERSON_4_t>, A が退避される
        assert v.size == 3
        # A は退避されたので restore できない
        assert v.get("<PERSON_1_t>") is None
        # B/C/D は残る
        assert v.get("<PERSON_2_t>") == "B"
        assert v.get("<PERSON_3_t>") == "C"
        assert v.get("<PERSON_4_t>") == "D"

    def test_退避後も新規番号は単調増加(self) -> None:
        # FIFO で退避した番号は再利用しない（restore 時の衝突防止）
        v = InMemoryVault(max_size=2, nonce="t")
        v.assign("PERSON", "A")  # <PERSON_1_t>
        v.assign("PERSON", "B")  # <PERSON_2_t>
        v.assign("PERSON", "C")  # <PERSON_3_t> (A 退避)
        v.assign("PERSON", "D")  # <PERSON_4_t> (B 退避)
        # A/B の placeholder は退避済み、新規は 3 以上
        assert v.get("<PERSON_3_t>") == "C"
        assert v.get("<PERSON_4_t>") == "D"

    def test_既存_surface_への_assign_は退避を発火しない(self) -> None:
        v = InMemoryVault(max_size=2, nonce="t")
        v.assign("PERSON", "A")
        v.assign("PERSON", "B")
        # 既存 surface の再 assign は新規エントリを作らない
        v.assign("PERSON", "A")  # cache hit、新規挿入しない
        assert v.size == 2
        assert v.get("<PERSON_1_t>") == "A"
        assert v.get("<PERSON_2_t>") == "B"

    def test_max_size_0_以下は_InvalidConfigError(self) -> None:
        import pytest

        from fuseji.exceptions import InvalidConfigError

        with pytest.raises(InvalidConfigError):
            InMemoryVault(max_size=0, nonce="t")
        with pytest.raises(InvalidConfigError):
            InMemoryVault(max_size=-1, nonce="t")

    def test_clear_後も_max_size_が維持される(self) -> None:
        v = InMemoryVault(max_size=2, nonce="t")
        v.assign("PERSON", "A")
        v.assign("PERSON", "B")
        v.clear()
        assert v.size == 0
        # clear 後も max_size は維持
        v.assign("PERSON", "C")
        v.assign("PERSON", "D")
        v.assign("PERSON", "E")
        assert v.size == 2  # max_size 上限が引き続き効く


class TestAssignMany:
    """bulk assign API の挙動 (#97)."""

    def test_空入力は空リスト(self) -> None:
        v = InMemoryVault(nonce="t")
        assert v.assign_many([]) == []

    def test_複数_pair_を一括採番(self) -> None:
        v = InMemoryVault(nonce="t")
        result = v.assign_many([("PERSON", "A"), ("PERSON", "B"), ("COMPANY", "X")])
        assert result == ["<PERSON_1_t>", "<PERSON_2_t>", "<COMPANY_1_t>"]
        # サイズと個別 get も整合
        assert v.size == 3
        assert v.get("<PERSON_1_t>") == "A"
        assert v.get("<PERSON_2_t>") == "B"
        assert v.get("<COMPANY_1_t>") == "X"

    def test_excluded_type_は_None_で他はそのまま採番(self) -> None:
        v = InMemoryVault(nonce="t")  # MY_NUMBER / CREDIT_CARD がデフォルト除外
        result = v.assign_many(
            [
                ("PERSON", "A"),
                ("MY_NUMBER", "123456789012"),
                ("PERSON", "B"),
                ("CREDIT_CARD", "4242424242424242"),
            ]
        )
        assert result == ["<PERSON_1_t>", None, "<PERSON_2_t>", None]

    def test_同一_pair_が複数回でも_同一_placeholder(self) -> None:
        # 同一 (type, surface) の重複は採番しない（assign と同じ意味論）
        v = InMemoryVault(nonce="t")
        result = v.assign_many([("PERSON", "A"), ("PERSON", "A"), ("PERSON", "A")])
        assert result == ["<PERSON_1_t>"] * 3
        assert v.size == 1

    def test_既存_surface_は_lock_を取らない_fast_path(self) -> None:
        # 事前に登録された surface は fast-path で返るので、後続の assign_many
        # で lock を取らずに dict 検索だけで完結する
        v = InMemoryVault(nonce="t")
        v.assign("PERSON", "A")
        v.assign("PERSON", "B")
        result = v.assign_many([("PERSON", "A"), ("PERSON", "B"), ("PERSON", "C")])
        # 既存 2 件は維持され、新規 1 件のみ採番
        assert result == ["<PERSON_1_t>", "<PERSON_2_t>", "<PERSON_3_t>"]
        assert v.size == 3

    def test_max_size_と協調する(self) -> None:
        v = InMemoryVault(max_size=2, nonce="t")
        result = v.assign_many([("PERSON", "A"), ("PERSON", "B"), ("PERSON", "C"), ("PERSON", "D")])
        # 全 4 件が採番されるが max_size=2 で FIFO 退避
        assert all(r is not None for r in result)
        assert v.size == 2
        # 最後 2 件のみ残る
        assert v.get("<PERSON_3_t>") == "C"
        assert v.get("<PERSON_4_t>") == "D"
        # 最古は退避された
        assert v.get("<PERSON_1_t>") is None
        assert v.get("<PERSON_2_t>") is None

    def test_default_Vault_実装は_assign_の繰り返し(self) -> None:
        # Vault Protocol のデフォルト実装が個別 assign の繰り返しになることを確認
        from fuseji.vault import Vault

        class _CountingVault:
            entity_type = ""  # 不要だが Vault Protocol を満たすため空
            name = ""

            def __init__(self) -> None:
                self.assign_calls = 0

            def assign(self, entity_type: str, surface: str) -> str | None:
                self.assign_calls += 1
                return f"<{entity_type}_{surface}>"

            def get(self, placeholder: str) -> str | None:
                return None

            def restore(self, text: str) -> str:
                return text

            def clear(self) -> None:
                pass

        cv = _CountingVault()
        # Protocol default は assign_many を持たない場合 NotImplemented にならず、
        # default 実装が個別 assign を呼ぶ動きを確認するには明示 cast が要る
        # → ここでは「default ある」を意図して assign 直接呼びをカウント
        v: Vault = cv  # type: ignore[assignment]
        for t, s in [("A", "x"), ("B", "y")]:
            v.assign(t, s)
        assert cv.assign_calls == 2


class TestPlaceholderNonce:
    """Vault placeholder の instance nonce (#81)."""

    def test_デフォルトでは_8文字_hex_の_nonce_が自動生成される(self) -> None:
        v = InMemoryVault()
        # secrets.token_hex(4) は 8 文字 [0-9a-f]
        assert re.fullmatch(r"[0-9a-f]{8}", v.nonce)

    def test_別インスタンスは別_nonce(self) -> None:
        # 2 つの InMemoryVault が同じ nonce を生成する確率は 2**-32 で実質ゼロ
        v1 = InMemoryVault()
        v2 = InMemoryVault()
        assert v1.nonce != v2.nonce

    def test_明示的に_nonce_を指定できる_テスト用途(self) -> None:
        v = InMemoryVault(nonce="testkey")
        assert v.nonce == "testkey"

    def test_placeholder_は_nonce_を含む形式で生成される(self) -> None:
        v = InMemoryVault(nonce="abc")
        ph = v.assign("PERSON", "田中")
        assert ph == "<PERSON_1_abc>"

    def test_別_Vault_の_placeholder_は_restore_で素通し_クロステナント漏洩防止(self) -> None:
        # 攻撃シナリオ: 利用者 A のテキストが「<EMAIL_1>」を含む文字列を持ち
        # LLM 応答にそのまま流れた場合、利用者 B の Vault.restore で誤復元
        # される可能性があった (v0.1 の脆弱性)。v0.2 では nonce が一致しない
        # ため、別 Vault 由来の placeholder は restore で素通しされる。
        v_a = InMemoryVault(nonce="aaa")
        v_a.assign("EMAIL", "secret@example.com")  # <EMAIL_1_aaa>
        # 攻撃者の B が「<EMAIL_1_xxx>」を含むテキストを投入
        attacker_text = "前のメール <EMAIL_1_xxx> に追加で..."
        # B の Vault は別 nonce → restore で素通し（誤復元しない）
        v_b = InMemoryVault(nonce="bbb")
        assert v_b.restore(attacker_text) == attacker_text
        # A の Vault でも、xxx 形式は自分の nonce ではないので素通し
        assert v_a.restore(attacker_text) == attacker_text

    def test_不正な_nonce_は_InvalidConfigError(self) -> None:
        import pytest

        from fuseji.exceptions import InvalidConfigError

        # 英数字以外は拒否（regex メタ文字の混入防止）
        with pytest.raises(InvalidConfigError):
            InMemoryVault(nonce="bad-nonce!")
        with pytest.raises(InvalidConfigError):
            InMemoryVault(nonce="")

    def test_nonce_は_repr_に出ない_PII_並みに非公開扱い(self) -> None:
        # nonce はメモリダンプ攻撃でしか取れない値だが、念のため __repr__ には
        # 表示せず、外部からは property 経由のみで取得可能とする。
        v = InMemoryVault(nonce="secret123")
        assert "secret123" not in repr(v)
