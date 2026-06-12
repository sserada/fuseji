"""カスタム Recognizer の最小 runnable サンプル (#197).

自社専用 ID (ここでは社員番号 ``EMP-XXXXXX``、6 桁数字) を検出する
カスタム認識器を `fuseji.recognizers.base.Recognizer` Protocol で実装し、
既存の `default_recognizers()` と組み合わせて `Masker` に組み込む。

実行::

    python main.py

期待出力::

    EMPLOYEE_ID  EMP-123456  score=0.9 (検証 OK)
    EMPLOYEE_ID  EMP-100000  score=0.5 (recall 優先、検証 NG)
    EMAIL        taro@example.com  score=1.0 (default_recognizers)

ポイント:

1. `entity_type` / `name` 属性で type 名と認識器識別子を宣言
2. `analyze(text, *, normalized=None)` で `Iterator[Entity]` を返す
3. `regex_analyze` ヘルパで正規表現 + 検証関数の組み合わせを最小ボイラープレートで書ける
4. `default_recognizers()` と list 結合して `Masker(recognizers=...)` に渡せば共存
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from fuseji import Masker
from fuseji.recognizers.base import default_recognizers, regex_analyze
from fuseji.types import Entity

# カスタム entity type 名 (任意。Presidio 等と integrate する際は `JP_*` 接頭辞推奨)
EMPLOYEE_ID = "EMPLOYEE_ID"

# パターン: EMP- + 6 桁数字 (`re.compile` を 1 度だけ評価する慣用)
_EMP_ID_PATTERN = re.compile(r"EMP-\d{6}")


def _validate_emp_id(digits: str) -> float | None:
    """検証関数: 正規表現マッチ後の 13 文字列に対し score を返す.

    本サンプルでは「100000 < 番号 < 999999 (擬似的に "有効範囲")」を OK 判定。
    実環境では発番台帳との照合・チェックディジット検証等を入れる。

    - 検証 OK → 0.9
    - 検証 NG だが形式は合う → 0.5 (recall 優先)
    """
    # マッチした surface 全体 `EMP-XXXXXX` を受け取る (regex_analyze の慣用)
    digits_only = digits[4:]
    if not digits_only.isdigit():
        return None  # マッチを破棄 (本パターンでは到達しないが念のため)
    n = int(digits_only)
    if 100001 <= n <= 999998:
        return 0.9
    return 0.5  # 形式は合うが範囲外 → 低スコアで残す


class EmployeeIdRecognizer:
    """社員番号 ``EMP-XXXXXX`` 認識器 (カスタム例).

    fuseji.recognizers.base.Recognizer Protocol を満たす最小実装。
    `regex_analyze` ヘルパで boilerplate (オフセット計算 / Entity 構築 /
    `normalized` kwarg ハンドリング / digit boundary 判定) を吸収する。
    """

    entity_type = EMPLOYEE_ID
    name = "employee_id"

    def analyze(self, text: str, *, normalized: str | None = None) -> Iterator[Entity]:
        return regex_analyze(
            text,
            entity_type=self.entity_type,
            recognizer_name=self.name,
            pattern=_EMP_ID_PATTERN,
            validate=_validate_emp_id,
            normalized=normalized,
            # require_digit_boundary=False がデフォルト (EMP- prefix で区切られるため不要)
        )


def main() -> None:
    # default_recognizers (5 種: MY_NUMBER, JP_PHONE_NUMBER, JP_POSTAL_CODE, EMAIL, CREDIT_CARD)
    # に EmployeeIdRecognizer を追加して 6 種で検出。
    masker = Masker(recognizers=[*default_recognizers(), EmployeeIdRecognizer()])

    text = (
        "担当 EMP-123456 へ。連絡先 taro@example.com、テスト用 EMP-100000 (範囲外想定) も記録する。"
    )
    result = masker.detect(text)
    for e in sorted(result, key=lambda x: x.start):
        # entity.text は属性参照経由で原 surface を取れる
        # (repr は #144 で PII safe な要約に変更されているので注意)
        print(f"{e.type:12s} {e.text:20s} score={e.score} recognizer={e.recognizer}")


if __name__ == "__main__":
    main()
