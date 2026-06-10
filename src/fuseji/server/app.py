"""FastAPI サーバー — /mask, /detect, /healthz エンドポイントを提供する."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from ..engine import Masker

app: FastAPI = FastAPI(
    title="fuseji",
    description="日本語特化の PII 検出・マスキングミドルウェア",
    version="0.0.0",
)

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
