"""GiNZA バックエンドで人名（PERSON）も検出するサンプル."""

from __future__ import annotations

from fuseji import Masker
from fuseji.ner.ginza import GinzaBackend


def main() -> None:
    masker = Masker(ner=GinzaBackend())

    text = "山田太郎さん(連絡先: 090-1234-5678, taro@example.co.jp)"

    # 検出
    print("=== 検出 ===")
    for entity in masker.detect(text):
        print(f"  {entity.text} ({entity.type}, score={entity.score})")

    # マスク
    print("\n=== マスク結果 ===")
    result = masker.mask(text)
    print(f"  {result.text}")
    print()
    print(f"  mapping: {dict(result.mapping)}")


if __name__ == "__main__":
    main()
