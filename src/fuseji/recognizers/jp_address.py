"""日本の住所認識器 (#127, opt-in, best-effort minimal version).

**設計方針 (v0.3 minimum viable)**:
- 47 都道府県名を必須 anchor として使用（地名のみの偽陽性を抑制）
- 都道府県の直後に市区町村 + 任意の番地 (`\\d+(?:[-－]\\d+)*(?:番地?|号)?`) を許容
- マンション・ビル名は対象外（過剰 recall を避ける）
- コンテキスト語（住所、在所、居住地など）周辺で score boost

**精度ターゲット**: 明示的な「都道府県 + 市区町村 + 番地」フォーマットでの recall を狙う。
住所の表記揺れすべてを拾う dictionary-based 検出は将来の Issue で扱う
（jageocoder / normalize-japanese-addresses 系の評価が必要、`docs/design.md` §9）。

**default_recognizers() には含めない**: 精度が他認識器より劣るため、明示的な
組み込みのみとする。
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..entity_types import JP_ADDRESS
from ..types import Entity
from .base import normalize

# 47 都道府県（公式表記）。順序は北 → 南。
_PREFECTURES: tuple[str, ...] = (
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
)

# 都道府県の alternation。「神奈川県」のような長いものから順に書いて部分一致を避ける。
_PREF_ALT = "|".join(sorted(_PREFECTURES, key=len, reverse=True))

# 市区町村パターン: 漢字・ひらがな・カタカナの連続 + 市/区/町/村/郡 で終わる
_CITY_PATTERN = r"[一-鿿぀-ゟ゠-ヿ々ヶ]+(?:市|区|町|村|郡)"

# 市区町村の後の地名（町名 / 字 など）: 漢字・かな・カタカナの連続
# 番地（数字）を含まないことで「番地が来たら止める」境界を作る
_PLACE_NAME_PATTERN = r"[一-鿿぀-ゟ゠-ヿ々ヶ]*"

# 番地パターン: 数字（区切り `-`）+ 任意の「番」「番地」「号」「丁目」サフィックス
# 全角ハイフン類は normalize で `-` に統一済みの前提
_BANCHI_PATTERN = r"\d+(?:-\d+){0,3}(?:番地?|号|丁目)?"

# 全体パターン: 都道府県 + 市区町村 + 地名(漢字/かな、任意) + 番地(数字、任意)
# 地名と番地を独立させることで「住所...です」の「です」を greedy に呑み込む問題を回避
_ADDRESS_PATTERN = re.compile(
    rf"(?:{_PREF_ALT}){_CITY_PATTERN}{_PLACE_NAME_PATTERN}(?:{_BANCHI_PATTERN})?"
)

# コンテキスト語: 周辺にあれば address らしさが増す（postal code 認識器と同方針）
_CONTEXT_WORDS: tuple[str, ...] = ("住所", "在所", "居住地", "所在地", "address")
_CONTEXT_WINDOW = 20


def _has_context(text: str, start: int, end: int) -> bool:
    around = text[max(0, start - _CONTEXT_WINDOW) : end + _CONTEXT_WINDOW]
    return any(w in around for w in _CONTEXT_WORDS)


class JpAddressRecognizer:
    """日本の住所認識器 (#127, opt-in)。

    検出パターン（**minimal viable, v0.3 開始版**）:

    - 47 都道府県名で必須 anchor
    - 直後に市区町村（漢字・かな + 市/区/町/村/郡）が必須
    - 任意で番地（``1-2-3 番地`` 等）

    スコア:
    - 都道府県 + 市区町村 + 番地 + コンテキスト語: 0.9
    - 都道府県 + 市区町村 + 番地: 0.7
    - 都道府県 + 市区町村 のみ: 0.5（recall 寄り）

    Example:
        >>> from fuseji import Masker
        >>> from fuseji.recognizers.base import default_recognizers
        >>> from fuseji.recognizers.jp_address import JpAddressRecognizer
        >>> masker = Masker(
        ...     recognizers=[*default_recognizers(), JpAddressRecognizer()]
        ... )
        >>> result = masker.detect("住所は東京都千代田区千代田1-1です")
        >>> sorted({e.type for e in result})
        ['JP_ADDRESS']

    **制限事項**:
    - マンション・ビル名は対象外（過剰 recall 抑制）
    - 都道府県を省略した住所（「千代田区千代田1-1」など）は検出しない
    - 表記揺れ（「壱丁目」「弐番地」等の漢数字）には対応せず
    - dictionary-based 高精度検出は将来の Issue で対応予定
    """

    entity_type = JP_ADDRESS
    name = "jp_address"

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterator[Entity]:
        target = normalized if normalized is not None else normalize(text)
        for m in _ADDRESS_PATTERN.finditer(target):
            start, end = m.start(), m.end()
            # 直前が漢字なら別の地名 (例: ○○東京都...) の連続として除外する
            # （都道府県名の単独性を担保）。
            if start > 0 and _is_kanji(target[start - 1]):
                continue
            # 番地の直後に数字を含む 1 番地 2 号のようなケースは「2 号」を取りこぼすが、
            # has_digit_boundary を適用すると正当な住所まで弾いてしまうため適用しない。
            matched_text = text[start:end]
            # 番地が含まれているか判定（数字の連続で粗く判断）
            has_banchi = any(c.isdigit() for c in matched_text)
            in_context = _has_context(target, start, end)
            if has_banchi and in_context:
                score = 0.9
            elif has_banchi:
                score = 0.7
            else:
                score = 0.5
            yield Entity(
                type=self.entity_type,
                text=matched_text,
                start=start,
                end=end,
                score=score,
                recognizer=self.name,
            )


def _is_kanji(ch: str) -> bool:
    return "一" <= ch <= "鿿"


__all__ = ["JpAddressRecognizer"]
