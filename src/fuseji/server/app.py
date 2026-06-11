"""FastAPI サーバー — /mask, /detect, /healthz エンドポイントを提供する."""

from __future__ import annotations

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


app: FastAPI = FastAPI(
    title="fuseji",
    description="日本語特化の PII 検出・マスキングミドルウェア",
    version="0.1.0",
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=_max_body_bytes_from_env())

# モジュールスコープの Masker インスタンス。v0.1 は単純化のためグローバルで保持する。
_masker = Masker()


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


@app.post("/mask", response_model=MaskResponse)
def mask_endpoint(req: MaskRequest) -> MaskResponse:
    """JSON データを受け取り、マスク済みの同型データを返す。"""
    return MaskResponse(data=_masker.mask_json(req.data))


@app.post("/detect", response_model=DetectResponse)
def detect_endpoint(req: DetectRequest) -> DetectResponse:
    """テキストから PII を検出して entity 一覧を返す。"""
    entities = _masker.detect(req.text)
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


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """ヘルスチェック。常に 200 OK を返す。"""
    return HealthResponse(status="ok")
