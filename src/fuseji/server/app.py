"""FastAPI サーバー — /mask, /detect, /healthz エンドポイントを提供する."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..engine import Masker

# デフォルトのリクエストボディサイズ上限（1 MB）。環境変数で上書き可能。
DEFAULT_MAX_BODY_BYTES: int = 1_000_000
_ENV_MAX_BODY = "FUSEJI_SERVER_MAX_BODY_BYTES"

# デフォルトのリクエストタイムアウト（秒）。環境変数で上書き可能。
DEFAULT_TIMEOUT_SECONDS: float = 30.0
_ENV_TIMEOUT = "FUSEJI_SERVER_TIMEOUT_SECONDS"


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Content-Length が上限を超える要求を 413 で拒否するミドルウェア。

    Content-Length ヘッダが付かない chunked エンコーディング等には対応しない
    （reverse-proxy 側で別途制限すること）。
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self._max_bytes:
                    return JSONResponse(
                        {"detail": "payload too large"},
                        status_code=413,
                    )
            except ValueError:
                # 不正な Content-Length は通常 starlette が 400 にする。素通し。
                pass
        return await call_next(request)


def _max_body_bytes_from_env() -> int:
    raw = os.environ.get(_ENV_MAX_BODY)
    if raw is None:
        return DEFAULT_MAX_BODY_BYTES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_BODY_BYTES
    return value if value > 0 else DEFAULT_MAX_BODY_BYTES


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
    raw = os.environ.get(_ENV_TIMEOUT)
    if raw is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


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
        version="0.1.0",
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
