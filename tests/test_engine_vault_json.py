"""engine.py の vault 統合と mask_json のテスト."""

from __future__ import annotations

from fuseji.engine import Masker
from fuseji.vault import InMemoryVault


class TestMaskerWithVault:
    def test_同一表層形は同一_placeholder(self) -> None:
        vault = InMemoryVault(nonce="t")
        m = Masker(vault=vault)
        # 同一メールアドレスを 2 回出す
        result = m.mask("a@b.com と a@b.com")
        # 両方とも <EMAIL_1_t>
        assert result.text == "<EMAIL_1_t> と <EMAIL_1_t>"
        assert result.mapping["<EMAIL_1_t>"] == "a@b.com"

    def test_セッションを跨いだ一貫性(self) -> None:
        vault = InMemoryVault(nonce="t")
        m = Masker(vault=vault)
        # 別の mask() 呼び出しでも同じ surface には同じ placeholder
        r1 = m.mask("最初: a@b.com")
        r2 = m.mask("2 回目: a@b.com")
        assert "<EMAIL_1_t>" in r1.text
        assert "<EMAIL_1_t>" in r2.text

    def test_異なる_surface_は別番号(self) -> None:
        vault = InMemoryVault(nonce="t")
        m = Masker(vault=vault)
        result = m.mask("a@b.com と c@d.com")
        assert "<EMAIL_1_t>" in result.text
        assert "<EMAIL_2_t>" in result.text

    def test_excluded_type_はマッピングに残らない(self) -> None:
        vault = InMemoryVault(nonce="t")  # MY_NUMBER がデフォルト除外
        m = Masker(vault=vault)
        result = m.mask("マイナンバー 123456789018")
        # MY_NUMBER は番号なしの <TYPE> 形式
        assert "<MY_NUMBER>" in result.text
        # mapping には残らない（復元不可）
        assert "<MY_NUMBER>" not in result.mapping

    def test_restore_でラウンドトリップ(self) -> None:
        vault = InMemoryVault(nonce="t")
        m = Masker(vault=vault)
        original = "メールは a@b.com です"
        masked = m.mask(original)
        restored = vault.restore(masked.text)
        assert restored == original


class TestMaskJson:
    def test_str_は_mask_される(self) -> None:
        m = Masker()
        result = m.mask_json("メール: a@b.com")
        assert "<EMAIL_1>" in result

    def test_dict_の値が_mask_される(self) -> None:
        m = Masker()
        data = {"name": "山田", "email": "a@b.com"}
        result = m.mask_json(data)
        assert result["name"] == "山田"
        assert "<EMAIL_1>" in result["email"]

    def test_dict_のキーは_mask_されない(self) -> None:
        m = Masker()
        data = {"a@b.com": "value"}
        result = m.mask_json(data)
        # キーはそのまま
        assert "a@b.com" in result

    def test_list_の要素が_mask_される(self) -> None:
        m = Masker()
        data = ["a@b.com", "c@d.com"]
        result = m.mask_json(data)
        assert all("<EMAIL_" in s for s in result)

    def test_ネストした構造(self) -> None:
        m = Masker()
        data = {"users": [{"email": "a@b.com"}, {"email": "c@d.com"}]}
        result = m.mask_json(data)
        # vault なしでは各 mask() 呼び出しは独立、各値内では <EMAIL_1>
        assert "<EMAIL_1>" in result["users"][0]["email"]
        assert "<EMAIL_1>" in result["users"][1]["email"]

    def test_vault_ありなら異なる_surface_は別番号_across_calls(self) -> None:
        m = Masker(vault=InMemoryVault(nonce="t"))
        data = ["a@b.com", "c@d.com"]
        result = m.mask_json(data)
        assert "<EMAIL_1_t>" in result[0]
        assert "<EMAIL_2_t>" in result[1]

    def test_非対象型は素通し(self) -> None:
        m = Masker()
        data = {"n": 42, "f": 3.14, "b": True, "none": None}
        result = m.mask_json(data)
        assert result == data

    def test_tuple_も再帰(self) -> None:
        m = Masker()
        data = ("a@b.com",)
        result = m.mask_json(data)
        assert isinstance(result, tuple)
        assert "<EMAIL_1>" in result[0]

    def test_深いネストは_too_deep_に_fail_closed(self) -> None:
        # max_json_depth=3 に絞り、4 段以上は固定文字列に置換されることを確認
        m = Masker(max_json_depth=3)
        data: object = {"l1": {"l2": {"l3": {"l4": "a@b.com"}}}}
        result = m.mask_json(data)
        # l4 のネスト先が too-deep 置換される
        assert "[fuseji: too deep]" in str(result)
        # 元データの a@b.com は漏れない（fail-closed）
        assert "a@b.com" not in str(result)

    def test_深度制限内ならマスクされる(self) -> None:
        m = Masker(max_json_depth=10)
        data = {"l1": {"l2": {"l3": "a@b.com"}}}
        result = m.mask_json(data)
        assert "<EMAIL_1>" in result["l1"]["l2"]["l3"]

    def test_境界_max_json_depth_N_では_N_段ぎりぎりまで許容(self) -> None:
        # max_json_depth=2: depth 0,1 のみ許容、depth 2 で fail-closed
        # ルート dict(depth=0) → 値 dict(depth=1 で処理) → その値文字列(depth=2 で too_deep)
        m = Masker(max_json_depth=2)
        data = {"l1": {"l2": "a@b.com"}}
        result = m.mask_json(data)
        # l2 の値（文字列）が depth=2 に達して too_deep
        assert result == {"l1": {"l2": "[fuseji: too deep]"}}

    def test_境界_max_json_depth_1_ではルート値のみ_too_deep(self) -> None:
        # max_json_depth=1: depth 0 のみ処理、depth 1 で fail-closed
        m = Masker(max_json_depth=1)
        # ルート dict は depth=0 で処理されるが、値は depth=1 で too_deep
        result = m.mask_json({"x": "a@b.com"})
        assert result == {"x": "[fuseji: too deep]"}

    def test_境界_max_json_depth_0_ではルート自体_too_deep(self) -> None:
        # max_json_depth=0: 何も再帰せず、ルート自体が too_deep
        m = Masker(max_json_depth=0)
        result = m.mask_json("a@b.com")
        assert result == "[fuseji: too deep]"

    def test_スカラ値はネストカウントしない_深度_0_OK(self) -> None:
        # ルートが str の場合、depth=0 で処理されてマスクされる
        m = Masker(max_json_depth=1)
        result = m.mask_json("メール: a@b.com")
        assert "<EMAIL_1>" in result

    def test_自己参照_dict_は_too_deep_で停止する(self) -> None:
        # 循環参照は max_json_depth に達した時点で fail-closed
        # 無限再帰せず必ず有限時間で完了することを保証
        m = Masker(max_json_depth=5)
        d: dict[str, object] = {}
        d["self"] = d
        result = m.mask_json(d)
        # depth 5 で too-deep に達し、内側が固定文字列に置換される
        assert "[fuseji: too deep]" in str(result)

    def test_bytes_は素通しされる現状仕様(self) -> None:
        # 非対象型として bytes はそのまま返る（マスクされない）。
        # NOTE: これは v0.2 時点の明示的な仕様。bytes 経由で PII が漏れる経路は
        # 別 Issue で対処予定（呼び出し側が bytes を decode してから mask_json に
        # 渡す責任を持つ）。
        m = Masker()
        result = m.mask_json(b"taro@example.com")
        assert result == b"taro@example.com"

    def test_set_は素通しされる現状仕様(self) -> None:
        # set / frozenset も JSON 互換型ではないので素通し（マスクされない）。
        # 呼び出し側が list 化してから mask_json に渡す責任を持つ。
        m = Masker()
        data = {"a@b.com", "c@d.com"}
        result = m.mask_json(data)
        assert result == data
        assert isinstance(result, set)

    def test_frozenset_も素通し(self) -> None:
        m = Masker()
        data = frozenset({"a@b.com"})
        result = m.mask_json(data)
        assert result == data
        assert isinstance(result, frozenset)

    def test_dict_キーは_mask_dict_keys_False_では素通し(self) -> None:
        # デフォルト挙動（v0.1 互換）: キーは PII を含まない前提で素通し。
        # 動的キーに PII が入る用途では mask_dict_keys=True を明示する（#85）。
        m = Masker()  # mask_dict_keys=False (デフォルト)
        result = m.mask_json({"taro@example.com": "value"})
        assert "taro@example.com" in result

    def test_dict_キーは_mask_dict_keys_True_でマスクされる(self) -> None:
        # mask_dict_keys=True: 動的キーに PII が混入する場合のセキュアモード
        m = Masker(mask_dict_keys=True)
        result = m.mask_json({"taro@example.com": "value"})
        # キーが <EMAIL_1> 形式にマスクされ、元の PII は残らない
        assert "taro@example.com" not in str(result)
        # 唯一のキーがマスクされていることを確認
        assert len(result) == 1
        key = next(iter(result.keys()))
        assert "<EMAIL_" in key

    def test_dict_キーマスクで衝突したらサフィックスで一意化(self) -> None:
        # 2 つの異なる surface でも同じハッシュ・同じ placeholder にはならないが、
        # mask の戻り値が同じになるケース（例: 同じ PII 文字列が複数のキーに）に
        # 対する衝突回避を確認
        m = Masker(mask_dict_keys=True)
        result = m.mask_json(
            {
                "taro@example.com": "v1",
                "taro@example.com extra": "v2",  # 部分的に同じ PII を含む別キー
            }
        )
        # キーが 2 つ残ること（情報が失われない）
        assert len(result) == 2

    def test_dict_キーの_masked_text_が完全一致したら___N_サフィックス(self) -> None:
        # 異なる surface の mask() 結果が完全に同じになるケースで、
        # サフィックスによる一意化パスを通す。Placeholder 戦略は call ごとに
        # 番号を 1 から振るため、同じ entity_type の単独キー 2 つは両方 `<EMAIL_1>`
        # にマスクされる。
        m = Masker(mask_dict_keys=True)
        result = m.mask_json({"a@b.com": "v1", "c@d.com": "v2"})
        # 2 件とも保存される（衝突回避による）
        assert len(result) == 2
        keys = list(result.keys())
        # 1 つは <EMAIL_1>、もう 1 つは <EMAIL_1>__2 のサフィックス付き
        assert "<EMAIL_1>" in keys
        assert "<EMAIL_1>__2" in keys
        # 値が両方残る
        assert set(result.values()) == {"v1", "v2"}

    def test_mask_dict_keys_True_でも非_str_キーは素通し(self) -> None:
        # int / tuple など str 以外のキーはマスクできないので素通し
        m = Masker(mask_dict_keys=True)
        result = m.mask_json({42: "taro@example.com", (1, 2): "v"})
        assert 42 in result
        assert (1, 2) in result
        # 値の方はマスクされる
        assert "<EMAIL_1>" in result[42]

    def test_mask_dict_keys_True_でも値のマスクは継続(self) -> None:
        m = Masker(mask_dict_keys=True)
        result = m.mask_json({"普通のキー": "メール: a@b.com"})
        # キーは PII なしなのでマスク結果は同じ文字列
        assert "普通のキー" in result
        assert "<EMAIL_1>" in result["普通のキー"]

    def test_int_float_bool_None_は素通し(self) -> None:
        # スカラ型は対象外で素通し
        m = Masker()
        for v in [42, 3.14, True, False, None]:
            assert m.mask_json(v) == v

    def test_dict_の値がさまざまな型でも安全(self) -> None:
        # 混在型 dict
        m = Masker()
        data = {
            "email": "taro@example.com",
            "age": 30,
            "active": True,
            "tags": ["urgent", "a@b.com"],
            "meta": None,
        }
        result = m.mask_json(data)
        # email 値はマスクされる
        assert "<EMAIL_1>" in result["email"]
        # スカラはそのまま
        assert result["age"] == 30
        assert result["active"] is True
        assert result["meta"] is None
        # list 内の email はマスク
        assert any("<EMAIL_" in s for s in result["tags"])
