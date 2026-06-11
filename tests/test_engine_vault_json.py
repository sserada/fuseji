"""engine.py の vault 統合と mask_json のテスト."""

from __future__ import annotations

from fuseji.engine import Masker
from fuseji.vault import InMemoryVault


class TestMaskerWithVault:
    def test_同一表層形は同一_placeholder(self) -> None:
        vault = InMemoryVault()
        m = Masker(vault=vault)
        # 同一メールアドレスを 2 回出す
        result = m.mask("a@b.com と a@b.com")
        # 両方とも <EMAIL_1>
        assert result.text == "<EMAIL_1> と <EMAIL_1>"
        assert result.mapping["<EMAIL_1>"] == "a@b.com"

    def test_セッションを跨いだ一貫性(self) -> None:
        vault = InMemoryVault()
        m = Masker(vault=vault)
        # 別の mask() 呼び出しでも同じ surface には同じ placeholder
        r1 = m.mask("最初: a@b.com")
        r2 = m.mask("2 回目: a@b.com")
        assert "<EMAIL_1>" in r1.text
        assert "<EMAIL_1>" in r2.text

    def test_異なる_surface_は別番号(self) -> None:
        vault = InMemoryVault()
        m = Masker(vault=vault)
        result = m.mask("a@b.com と c@d.com")
        assert "<EMAIL_1>" in result.text
        assert "<EMAIL_2>" in result.text

    def test_excluded_type_はマッピングに残らない(self) -> None:
        vault = InMemoryVault()  # MY_NUMBER がデフォルト除外
        m = Masker(vault=vault)
        result = m.mask("マイナンバー 123456789018")
        # MY_NUMBER は番号なしの <TYPE> 形式
        assert "<MY_NUMBER>" in result.text
        # mapping には残らない（復元不可）
        assert "<MY_NUMBER>" not in result.mapping

    def test_restore_でラウンドトリップ(self) -> None:
        vault = InMemoryVault()
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
        m = Masker(vault=InMemoryVault())
        data = ["a@b.com", "c@d.com"]
        result = m.mask_json(data)
        assert "<EMAIL_1>" in result[0]
        assert "<EMAIL_2>" in result[1]

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
