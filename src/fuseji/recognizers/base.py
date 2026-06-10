"""Recognizer プロトコルと共通の正規化ユーティリティ."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..types import Entity


class Recognizer(Protocol):
    """PII 認識器のプロトコル。

    属性:
        entity_type: 認識する種別名（例: ``"EMAIL"``, ``"JP_PHONE_NUMBER"``）

    メソッド:
        analyze: テキストを走査し検出した `Entity` を返す。
    """

    entity_type: str

    def analyze(self, text: str) -> Iterable[Entity]: ...


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
    """数字とハイフンの両方を正規化。"""
    return text.translate(_DIGIT_TRANSLATION).translate(_HYPHEN_TRANSLATION)


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
