"""FastAPI サーバー — /mask, /detect, /healthz エンドポイントを提供する."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import __version__
from ..engine import Masker

# デフォルトのリクエストボディサイズ上限（1 MB）。環境変数で上書き可能。
DEFAULT_MAX_BODY_BYTES: int = 1_000_000
_ENV_MAX_BODY = "FUSEJI_SERVER_MAX_BODY_BYTES"

# デフォルトのリクエストタイムアウト（秒）。環境変数で上書き可能。
DEFAULT_TIMEOUT_SECONDS: float = 30.0
_ENV_TIMEOUT = "FUSEJI_SERVER_TIMEOUT_SECONDS"


class BodySizeLimitMiddleware:
    """リクエストボディサイズを上限で制限する pure ASGI ミドルウェア (#87)。

    Content-Length ヘッダ有無に関わらずボディ全体を逐次読み取り、累積バイト数が
    `max_bytes` を超えた時点で **下流アプリにボディを渡さず** 413 を返す。
    chunked transfer-encoding / HTTP/2 / Content-Length 省略の DoS 経路にも
    対応する。

    実装方針:
    1. Content-Length が宣言されていて max を超える場合は受信前に 413
    2. それ以外は `receive` をラップしてバイト数を累積カウント
    3. 上限を超えたらラッパーが 413 を送信し、上流アプリへの呼び出しを中止
    4. 上限内なら全 body を buffer し、replay 用の receive で下流に渡す
       （1MB 程度の bounded buffer なのでメモリ的に許容範囲）
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        # Content-Length 宣言済みなら受信前に弾く（fast path）
        headers = dict(scope.get("headers", []))
        cl_raw = headers.get(b"content-length")
        if cl_raw is not None:
            try:
                if int(cl_raw) > self._max_bytes:
                    await _send_413(send)
                    return
            except ValueError:
                # 不正な Content-Length は受信側で扱う
                pass
        # ボディを逐次読みつつ上限を判定。超過時は 413 を返して終了。
        body_chunks: list[bytes] = []
        total = 0
        more_body = True
        while more_body:
            msg = await receive()
            if msg["type"] != "http.request":
                # disconnect 等のイベント — 安全側で下流に渡さず終了
                return
            chunk = msg.get("body", b"")
            total += len(chunk)
            if total > self._max_bytes:
                await _send_413(send)
                return
            body_chunks.append(chunk)
            more_body = msg.get("more_body", False)
        buffered_body = b"".join(body_chunks)
        # 下流の receive を replay で 1 回だけボディを返すラッパーに置き換える。
        # disconnect イベントが来たら以降は本物の receive() に委譲。
        sent = False

        async def receive_buffered() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": buffered_body, "more_body": False}
            return await receive()

        await self._app(scope, receive_buffered, send)


async def _send_413(send: Send) -> None:
    """payload too large を JSON で返す ASGI 直接送信."""
    body = b'{"detail":"payload too large"}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


_T = TypeVar("_T", int, float)


def _positive_from_env(name: str, default: _T, cast: Callable[[str], _T]) -> _T:
    """環境変数から正の数値を読み取り、未設定・不正値・非正値はデフォルトを返す。

    本サーバーの上限系設定（body size / timeout）はいずれも正の値のみが意味を
    持つため、cast 失敗および <= 0 を同じ「無効」として扱う。
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = cast(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _max_body_bytes_from_env() -> int:
    return _positive_from_env(_ENV_MAX_BODY, DEFAULT_MAX_BODY_BYTES, int)


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """各リクエストの処理時間を制限し、超過時に 504 を返すミドルウェア。

    実装は `asyncio.wait_for` ベース。同期エンドポイントは Starlette の
    threadpool で実行されるため、タイムアウト発火時もスレッド側の処理は
    継続する（協調的キャンセル不可）。本ミドルウェアの目的はクライアント
    へのレスポンス時間を有界にすること（DoS 緩和）であり、CPU を確実に
    解放することではない点に注意。
    """

    def __init__(self, app: ASGIApp, timeout_seconds: float) -> None:
        super().__init__(app)
        self._timeout = timeout_seconds

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        try:
            return await asyncio.wait_for(call_next(request), timeout=self._timeout)
        except asyncio.TimeoutError:
            return JSONResponse(
                {"detail": "request timeout"},
                status_code=504,
            )


def _timeout_seconds_from_env() -> float:
    return _positive_from_env(_ENV_TIMEOUT, DEFAULT_TIMEOUT_SECONDS, float)


class MaskRequest(BaseModel):
    """`POST /mask` のリクエストボディ."""

    data: Any


class MaskResponse(BaseModel):
    """`POST /mask` のレスポンスボディ."""

    data: Any


class DetectRequest(BaseModel):
    """`POST /detect` のリクエストボディ."""

    text: str


class EntityModel(BaseModel):
    """検出された Entity の JSON 表現."""

    type: str
    text: str
    start: int
    end: int
    score: float
    recognizer: str


class DetectResponse(BaseModel):
    """`POST /detect` のレスポンスボディ."""

    entities: list[EntityModel]


class HealthResponse(BaseModel):
    """`GET /healthz` のレスポンスボディ."""

    status: str


def create_app(
    masker: Masker | None = None,
    *,
    max_body_bytes: int | None = None,
    timeout_seconds: float | None = None,
) -> FastAPI:
    """FastAPI アプリケーションを構築して返す（factory）。

    Args:
        masker: 使用する Masker インスタンス。`None` のとき新規に
            `Masker()` を作る（v0.1 デフォルト認識器セット）。
            カスタム認識器・Vault・NER を統合したい場合は明示的に渡す。
        max_body_bytes: リクエストボディサイズ上限（バイト）。`None` のとき
            環境変数 `FUSEJI_SERVER_MAX_BODY_BYTES` または既定 1MB。
        timeout_seconds: 1 リクエストあたりの処理時間上限（秒）。`None` のとき
            環境変数 `FUSEJI_SERVER_TIMEOUT_SECONDS` または既定 30 秒。
            超過時は HTTP 504 を返す。同期エンドポイントの threadpool 実行を
            真に中断するわけではなく、レスポンス時間の上限を保証する。

    Returns:
        ルート登録済みの `FastAPI` インスタンス。

    Example:
        >>> from fuseji import Masker, InMemoryVault
        >>> from fuseji.server.app import create_app
        >>> # Vault を使う構成でデプロイ
        >>> app = create_app(masker=Masker(vault=InMemoryVault()))
    """
    actual_masker: Masker = masker if masker is not None else Masker()
    actual_max_body: int = (
        max_body_bytes if max_body_bytes is not None else _max_body_bytes_from_env()
    )
    actual_timeout: float = (
        timeout_seconds if timeout_seconds is not None else _timeout_seconds_from_env()
    )

    new_app = FastAPI(
        title="fuseji",
        description="日本語特化の PII 検出・マスキングミドルウェア",
        version=__version__,
    )
    # ミドルウェアは登録順の逆順で外側に被さる。timeout を最外周（最後に登録）に
    # 置くと、body-size limit 内側の処理時間も含めて計測される。
    new_app.add_middleware(BodySizeLimitMiddleware, max_bytes=actual_max_body)
    new_app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=actual_timeout)

    @new_app.post("/mask", response_model=MaskResponse)
    def mask_endpoint(req: MaskRequest) -> MaskResponse:
        """JSON データを受け取り、マスク済みの同型データを返す。"""
        return MaskResponse(data=actual_masker.mask_json(req.data))

    @new_app.post("/detect", response_model=DetectResponse)
    def detect_endpoint(req: DetectRequest) -> DetectResponse:
        """テキストから PII を検出して entity 一覧を返す。"""
        entities = actual_masker.detect(req.text)
        return DetectResponse(
            entities=[
                EntityModel(
                    type=e.type,
                    text=e.text,
                    start=e.start,
                    end=e.end,
                    score=e.score,
                    recognizer=e.recognizer,
                )
                for e in entities
            ]
        )

    @new_app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        """ヘルスチェック。常に 200 OK を返す。"""
        return HealthResponse(status="ok")

    return new_app


# モジュールスコープの app は既定構成（環境変数からの max_body_bytes、新規 Masker）。
# `uvicorn fuseji.server.app:app` で起動する既存利用との後方互換のため残す。
# カスタム構成が必要なときは create_app(...) を呼んで自前で起動する。
app: FastAPI = create_app()
