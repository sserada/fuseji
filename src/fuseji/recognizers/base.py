"""Recognizer プロトコルと共通の正規化・ヘルパユーティリティ."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Protocol

from ..types import Entity

# 認識器間で共有するセパレーターパターン（ハイフン/空白）。各認識器が
# digits-only に正規化する際に使う。
SEPARATOR_PATTERN: re.Pattern[str] = re.compile(r"[-\s]")


class Recognizer(Protocol):
    """PII 認識器のプロトコル。

    属性:
        entity_type: 認識する種別名（例: ``"EMAIL"``, ``"JP_PHONE_NUMBER"``）
        name: 認識器の識別子（snake_case）。検出された `Entity.recognizer` に格納される

    メソッド:
        analyze: テキストを走査し検出した `Entity` を返す。

            `normalized` 引数には Masker 層で 1 回だけ計算した
            `normalize(text)`（全角→半角の数字・ハイフン正規化）が渡される。
            正規化を必要としない認識器（例: EMAIL）はこの引数を無視してよいが、
            v0.2 以降はシグネチャ上必ず受け取る必要がある（後方互換性のための
            inspect ベース dispatch を廃止）。
    """

    entity_type: str
    name: str

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterator[Entity]: ...


# --- 文字正規化テーブル ---
# いずれも 1 文字 ↔ 1 文字。codepoint 長が変わらないため、
# 正規化後オフセットは元テキストに対して維持される。

_DIGIT_TRANSLATION = str.maketrans("０１２３４５６７８９", "0123456789")

_HYPHEN_TRANSLATION = str.maketrans(
    {
        "‐": "-",  # U+2010 HYPHEN
        "‑": "-",  # U+2011 NON-BREAKING HYPHEN
        "‒": "-",  # U+2012 FIGURE DASH
        "–": "-",  # U+2013 EN DASH
        "—": "-",  # U+2014 EM DASH
        "―": "-",  # U+2015 HORIZONTAL BAR
        "−": "-",  # U+2212 MINUS SIGN
        "ー": "-",  # U+30FC KATAKANA-HIRAGANA PROLONGED SOUND MARK
        "－": "-",  # U+FF0D FULLWIDTH HYPHEN-MINUS
    }
)

# normalize() 用に digits + hyphens を 1 つの translate テーブルへマージ。
# 両者のキーは disjoint（数字と記号）なので衝突なし。値は数字側が int、
# ハイフン側が str（str.translate はどちらも受ける）。
_NORMALIZE_TRANSLATION: dict[int, str | int] = {
    **_DIGIT_TRANSLATION,
    **_HYPHEN_TRANSLATION,
}


def normalize_digits(text: str) -> str:
    """全角数字（０-９）を半角に変換。文字数は維持される。"""
    return text.translate(_DIGIT_TRANSLATION)


def normalize_hyphens(text: str) -> str:
    """各種ハイフン類を ASCII ハイフン `-` に変換。文字数は維持される。

    含まれる: U+2010 HYPHEN, U+2011 NON-BREAKING HYPHEN, U+2012 FIGURE DASH,
    U+2013 EN DASH, U+2014 EM DASH, U+2015 HORIZONTAL BAR, U+2212 MINUS SIGN,
    U+30FC KATAKANA-HIRAGANA PROLONGED SOUND MARK, U+FF0D FULLWIDTH HYPHEN-MINUS。
    """
    return text.translate(_HYPHEN_TRANSLATION)


def normalize(text: str) -> str:
    """数字とハイフンの両方を 1 パスで正規化。"""
    return text.translate(_NORMALIZE_TRANSLATION)


def has_digit_boundary(text: str, start: int, end: int) -> bool:
    """マッチ位置 [start, end) の直前または直後が数字なら True を返す。

    認識器がマッチ範囲を別 ID（より長い番号列）の一部と切り分けるためのヘルパ。
    True を返した場合、その候補は除外すべき。

    Args:
        text: 正規化後のテキスト（半角数字に統一されている前提）。
        start: マッチ開始位置（包含）。
        end: マッチ終端位置（除外）。
    """
    if start > 0 and text[start - 1].isdigit():
        return True
    if end < len(text) and text[end].isdigit():  # noqa: SIM103
        return True
    return False


# --- 共通テンプレート ---

# validate 関数の型: 候補文字列を受け取り、有効ならスコア、無効なら None を返す
ValidateFn = Callable[[str], "float | None"]


def regex_analyze(
    text: str,
    *,
    entity_type: str,
    recognizer_name: str,
    pattern: re.Pattern[str],
    default_score: float = 1.0,
    validate: ValidateFn | None = None,
    normalize_fn: Callable[[str], str] | None = None,
    normalized: str | None = None,
    require_digit_boundary: bool = False,
    strip_separators_before_validate: bool = False,
) -> Iterator[Entity]:
    """正規表現マッチ + 任意の検証ロジックで Entity を生成する共通テンプレート。

    regex ベースの認識器に共通する処理を集約する。各認識器はこの関数を
    呼ぶだけで、Entity 構築・正規化・桁境界判定・セパレーター除去などの
    定型処理を再実装する必要がなくなる。

    Args:
        text: 元テキスト。
        entity_type: 検出する種別名（例: ``"EMAIL"``）。
        recognizer_name: 認識器の識別子（snake_case）。`Entity.recognizer` に格納。
        pattern: マッチに使う正規表現。`normalize_fn` 指定時は正規化後テキストに適用。
        default_score: `validate=None` の場合に各マッチへ付与するスコア。
        validate: マッチを検証する関数。`None` 以外を返したマッチのみ採用しその値を score にする。
        normalize_fn: マッチ前にテキストへ適用する正規化（例: `normalize`, `normalize_digits`）。
            1 文字 ↔ 1 文字の変換のみ許容（オフセット維持のため）。
        normalized: 事前計算済みの正規化テキスト。指定時は `normalize_fn` を呼ばずに
            この値を使う（Masker 層で 1 回計算したものを各認識器で再利用するための最適化）。
            1 文字 ↔ 1 文字変換である前提（オフセット維持）。
        require_digit_boundary: True なら、マッチの直前/直後が数字の候補を除外。
        strip_separators_before_validate: True なら、validate に渡す前に `SEPARATOR_PATTERN` で
            ハイフン・空白を除去（digits-only に正規化）。

    Yields:
        検出された `Entity`。`text` は元テキストの表層形で返す（正規化後ではない）。
    """
    if normalized is not None:
        target = normalized
    elif normalize_fn is not None:
        target = normalize_fn(text)
    else:
        target = text
    for m in pattern.finditer(target):
        start, end = m.start(), m.end()
        if require_digit_boundary and has_digit_boundary(target, start, end):
            continue
        if validate is not None:
            candidate = m.group()
            if strip_separators_before_validate:
                candidate = SEPARATOR_PATTERN.sub("", candidate)
            score = validate(candidate)
            if score is None:
                continue
        else:
            score = default_score
        yield Entity(
            type=entity_type,
            text=text[start:end],
            start=start,
            end=end,
            score=score,
            recognizer=recognizer_name,
        )


def default_recognizers() -> tuple[Recognizer, ...]:
    """v0.1 のデフォルト認識器セット。

    EMAIL, CREDIT_CARD, MY_NUMBER, JP_PHONE_NUMBER, JP_POSTAL_CODE の順で返す。
    順序は Masker エンジン側のオーバーラップ解決には影響しない（スコア優先）。
    """
    # 循環インポート回避のため遅延 import
    from .credit_card import CreditCardRecognizer
    from .email import EmailRecognizer
    from .jp_phone import JpPhoneRecognizer
    from .jp_postal import JpPostalRecognizer
    from .my_number import MyNumberRecognizer

    return (
        EmailRecognizer(),
        CreditCardRecognizer(),
        MyNumberRecognizer(),
        JpPhoneRecognizer(),
        JpPostalRecognizer(),
    )
