"""Langfuse SDK + fuseji の最短サンプル."""

from __future__ import annotations

import os

from langfuse import Langfuse

from fuseji.integrations.langfuse import make_mask_fn


def main() -> None:
    # fuseji の mask 関数を Langfuse に差し込む
    langfuse = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        mask=make_mask_fn(),
    )

    # PII を含むプロンプト/応答を観測対象にする
    trace = langfuse.trace(
        name="fuseji-demo",
        input={
            "user": "山田",
            "message": (
                "問い合わせ番号 〒123-4567、"
                "連絡先 090-1234-5678 / taro@example.co.jp、"
                "マイナンバー 123456789018"
            ),
        },
        output={
            "reply": "ご連絡ありがとうございます。担当者からご返信いたします。",
        },
    )
    print(f"Trace ID: {trace.id}")
    print("Langfuse ダッシュボードで PII がマスクされていることを確認してください。")

    langfuse.flush()


if __name__ == "__main__":
    main()
