"""Property-based テスト (Hypothesis, #183).

example-based テストでは見落としやすい不変条件 (invariant) を、ランダム生成
入力に対して検証する。各 property は明確な不変式を一文で説明できるものに
絞る (Hypothesis の流儀)。

- `normalize`: 1 文字 ↔ 1 文字でオフセット維持
- `Hash` 戦略: 同一入力で決定的
- `InMemoryVault.assign`: 同一 (type, surface) で同一 placeholder (idempotent)
- `MyNumberRecognizer`: 12 桁以外の数字列はマッチしない
- `CorporateNumberRecognizer`: 13 桁以外の数字列はマッチしない
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from fuseji import InMemoryVault
from fuseji.recognizers.base import normalize, normalize_digits, normalize_hyphens
from fuseji.recognizers.corporate_number import CorporateNumberRecognizer
from fuseji.recognizers.my_number import MyNumberRecognizer
from fuseji.strategies import Hash
from fuseji.types import Entity

# CI ノイズを抑えるためデフォルト deadline をやや緩く設定 (1 example 最大 300ms)。
_settings = settings(max_examples=100, deadline=300)


# --- normalize --------------------------------------------------------------


@_settings
@given(st.text())
def test_normalize_は_文字数を変えない(text: str) -> None:
    """normalize は 1 文字 ↔ 1 文字でオフセット維持の前提を満たす."""
    assert len(normalize(text)) == len(text)


@_settings
@given(st.text())
def test_normalize_digits_は_文字数を変えない(text: str) -> None:
    assert len(normalize_digits(text)) == len(text)


@_settings
@given(st.text())
def test_normalize_hyphens_は_文字数を変えない(text: str) -> None:
    assert len(normalize_hyphens(text)) == len(text)


@_settings
@given(st.text(alphabet=string.ascii_letters + string.digits + " ", min_size=0, max_size=50))
def test_normalize_は_ASCII_数字入力で_恒等(text: str) -> None:
    """ASCII 文字 (英数字 + 空白) のみで構成された入力は不変."""
    assert normalize(text) == text


# --- Hash strategy ----------------------------------------------------------


@_settings
@given(
    text=st.text(min_size=1, max_size=50),
    length=st.integers(min_value=4, max_value=32),
)
def test_Hash_戦略は_決定的(text: str, length: int) -> None:
    """同一 surface, 同一 length で同一 hash を返す (SHA256 prefix)."""
    h1 = Hash(length=length)
    h2 = Hash(length=length)
    e = Entity(type="X", text=text, start=0, end=len(text), score=0.5, recognizer="r")
    masked1, _ = h1.mask(text, [e])
    masked2, _ = h2.mask(text, [e])
    assert masked1 == masked2


@_settings
@given(
    text=st.text(min_size=1, max_size=50),
    length=st.integers(min_value=8, max_value=32),
)
def test_Hash_出力長は_length_引数と一致(text: str, length: int) -> None:
    """Hash 戦略の置換後 placeholder 長は length と一致 (SHA256 prefix)."""
    h = Hash(length=length)
    e = Entity(type="X", text=text, start=0, end=len(text), score=0.5, recognizer="r")
    masked, _ = h.mask(text, [e])
    # masked は length 文字 hex に置換されたもののみで構成される
    assert len(masked) == length


# --- InMemoryVault ----------------------------------------------------------


@_settings
@given(
    entity_type=st.sampled_from(["EMAIL", "JP_PHONE_NUMBER", "JP_POSTAL_CODE", "CUSTOM"]),
    surface=st.text(min_size=1, max_size=50),
)
def test_Vault_assign_は_冪等(entity_type: str, surface: str) -> None:
    """同一 (type, surface) を複数回 assign しても同じ placeholder を返す."""
    # MY_NUMBER と CREDIT_CARD は DEFAULT_EXCLUDED で None を返す → property 対象外
    vault = InMemoryVault()
    p1 = vault.assign(entity_type, surface)
    p2 = vault.assign(entity_type, surface)
    p3 = vault.assign(entity_type, surface)
    assert p1 == p2 == p3


@_settings
@given(
    surfaces=st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=30, unique=True),
)
def test_Vault_assign_は_異なる_surface_に_異なる_placeholder(surfaces: list[str]) -> None:
    """unique な surface 群に対し placeholder も unique."""
    vault = InMemoryVault()
    placeholders = [vault.assign("EMAIL", s) for s in surfaces]
    # placeholder のすべてが None でない (EMAIL は excluded ではない)
    assert all(p is not None for p in placeholders)
    assert len(set(placeholders)) == len(surfaces)


# --- Recognizer length boundaries -----------------------------------------


# MyNumberRecognizer は **12 桁ちょうど** の数字列のみマッチする (#82 仕様)。
# property: 11 桁以下 or 13 桁以上の純粋数字列にはマッチしない (周辺非数字を必須にする)。


@_settings
@given(digits=st.text(alphabet="0123456789", min_size=1, max_size=11).filter(lambda s: len(s) >= 1))
def test_MyNumber_は_12桁未満の純粋数字列に_マッチしない(digits: str) -> None:
    # コンテキスト語を入れず周辺を空白で区切る → 12 桁チェックで弾かれる
    text = f"  {digits}  "
    entities = list(MyNumberRecognizer().analyze(text))
    assert entities == []


@_settings
@given(
    digits=st.text(alphabet="0123456789", min_size=14, max_size=20).filter(lambda s: len(s) >= 14)
)
def test_MyNumber_は_14桁以上で_digit_boundary_除外(digits: str) -> None:
    """14 桁以上の連続数字は has_digit_boundary で MY_NUMBER 候補から除外."""
    text = f"  {digits}  "
    entities = [e for e in MyNumberRecognizer().analyze(text) if e.type == "MY_NUMBER"]
    # 14 桁以上の純粋数字列は MY_NUMBER (12 桁) としては検出されない
    # (前後数字でない境界 = 数字が前後にある場合は除外される)
    assert entities == []


# CorporateNumberRecognizer も 13 桁ちょうど (公開仕様)。
@_settings
@given(digits=st.text(alphabet="0123456789", min_size=1, max_size=12).filter(lambda s: len(s) >= 1))
def test_CorporateNumber_は_13桁未満の純粋数字列に_マッチしない(digits: str) -> None:
    text = f"  {digits}  "
    entities = list(CorporateNumberRecognizer().analyze(text))
    assert entities == []
