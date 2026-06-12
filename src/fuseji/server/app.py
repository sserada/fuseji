"""FastAPI サーバー — /mask, /detect, /healthz エンドポイントを提供する."""

from __future__ import annotations

import asyncio
import hmac
import os
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .. import __version__
from ..engine import Masker

# デフォルトのリクエストボディサイズ上限（1 MB）。環境変数で上書き可能。
DEFAULT_MAX_BODY_BYTES: int = 1_000_000
_ENV_MAX_BODY = "FUSEJI_SERVER_MAX_BODY_BYTES"

# デフォルトのリクエストタイムアウト（秒）。環境変数で上書き可能。
DEFAULT_TIMEOUT_SECONDS: float = 30.0
_ENV_TIMEOUT = "FUSEJI_SERVER_TIMEOUT_SECONDS"

# API キー認証 (#83)。未設定なら無認証（reverse-proxy 側で対応する想定）。
_ENV_API_KEY = "FUSEJI_API_KEY"
# CORS allow_origins。未設定なら CORS 無効（同一オリジンのみ）。
_ENV_CORS_ORIGINS = "FUSEJI_CORS_ORIGINS"
# /detect レスポンスに原 PII surface を含めるか (#143)。デフォルト無効。
# `FUSEJI_DETECT_INCLUDE_SURFACE=1` で opt-in。create_app(detect_include_surface=True) でも可。
_ENV_DETECT_INCLUDE_SURFACE = "FUSEJI_DETECT_INCLUDE_SURFACE"
# 認証対象のパス（healthz / openapi.json は対象外で誰でも叩ける）
_PROTECTED_PATHS: frozenset[str] = frozenset({"/mask", "/detect"})

# /detect レスポンスで opt-in 時にも固定マスクする高センシティビティ type (#143)。
# FakerStrategy と同じ集合: 番号法対応 + Luhn 通過の架空 CC を扱わない。
_DETECT_FIXED_MASK_TYPES: frozenset[str] = frozenset(
    {"MY_NUMBER", "CREDIT_CARD", "CORPORATE_NUMBER"}
)
_DETECT_REDACTED_LABEL: str = "<redacted>"


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


def _api_key_from_env() -> str | None:
    """環境変数から API キーを読み取る。未設定/空文字なら None。"""
    raw = os.environ.get(_ENV_API_KEY)
    if raw is None or not raw.strip():
        return None
    return raw


def _detect_include_surface_from_env() -> bool:
    """環境変数 `FUSEJI_DETECT_INCLUDE_SURFACE` の真偽値解釈 (#143).

    `1` / `true` / `yes` / `on` を真扱い、それ以外（未設定含む）は偽。
    """
    raw = os.environ.get(_ENV_DETECT_INCLUDE_SURFACE)
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cors_origins_from_env() -> list[str] | None:
    """環境変数 `FUSEJI_CORS_ORIGINS` をカンマ区切りで読み取る。未設定なら None。

    例: `FUSEJI_CORS_ORIGINS=https://app.example.com,https://admin.example.com`
    """
    raw = os.environ.get(_ENV_CORS_ORIGINS)
    if raw is None or not raw.strip():
        return None
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class ApiKeyAuthMiddleware:
    """`X-API-Key` ヘッダで API キー認証を行う pure ASGI ミドルウェア (#83)。

    保護対象は `_PROTECTED_PATHS` (`/mask`, `/detect`) のみで、`/healthz` や
    OpenAPI スキーマは未認証で叩ける（ヘルスチェック・ドキュメント生成のため）。

    認証失敗時:
    - ヘッダ未設定 / 不一致: HTTP 401
    - キーは `hmac.compare_digest` で timing-safe に比較

    `create_app(api_key=...)` または環境変数 `FUSEJI_API_KEY` で設定する。
    未設定時は本ミドルウェアは登録されない（reverse-proxy 側で認証する想定）。
    """

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self._app = app
        self._api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path not in _PROTECTED_PATHS:
            await self._app(scope, receive, send)
            return
        # ヘッダを取り出して比較
        headers = dict(scope.get("headers", []))
        provided = headers.get(b"x-api-key")
        if provided is None or not hmac.compare_digest(provided, self._api_key.encode("utf-8")):
            await _send_401(send)
            return
        await self._app(scope, receive, send)


async def _send_401(send: Send) -> None:
    """unauthorized を JSON で返す ASGI 直接送信."""
    body = b'{"detail":"unauthorized"}'
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"www-authenticate", b'ApiKey realm="fuseji"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


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
    """検出された Entity の JSON 表現.

    `text` は省略可能 (#143)。デフォルトでは原 PII surface を返さない
    (`detect, never retain` 原則 / OWASP LLM02:2025 / CWE-200 への対応)。
    `create_app(detect_include_surface=True)` または環境変数
    `FUSEJI_DETECT_INCLUDE_SURFACE=1` で opt-in した場合のみ含める。
    """

    type: str
    text: str | None = None
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


def _resolve_detect_text(entity_type: str, surface: str, include_surface: bool) -> str | None:
    """/detect レスポンスの `text` フィールド値を決定する (#143).

    - `include_surface=False` (デフォルト): すべて None を返し、原 PII を露出させない
    - `include_surface=True`: 高センシティビティ type は `<redacted>` 固定マスク、
      それ以外は原 surface を返す
    """
    if not include_surface:
        return None
    if entity_type in _DETECT_FIXED_MASK_TYPES:
        return _DETECT_REDACTED_LABEL
    return surface


def create_app(
    masker: Masker | None = None,
    *,
    max_body_bytes: int | None = None,
    timeout_seconds: float | None = None,
    api_key: str | None = None,
    cors_origins: Sequence[str] | None = None,
    detect_include_surface: bool | None = None,
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
        api_key: API キー認証を有効化するキー文字列。`None` のとき環境変数
            `FUSEJI_API_KEY` から取得し、それも未設定なら無認証
            （reverse-proxy 側で認証する想定）。有効時は `X-API-Key` ヘッダで
            timing-safe 比較し、不一致なら HTTP 401。`/healthz` と OpenAPI は
            保護対象外。
        cors_origins: CORS で許可するオリジンのリスト。`None` のとき環境変数
            `FUSEJI_CORS_ORIGINS`（カンマ区切り）から取得し、それも未設定なら
            CORS 無効（同一オリジンのみ）。インターネット公開時の必須設定。
        detect_include_surface: `/detect` レスポンスに原 PII surface (`text`) を
            含めるか (#143)。`None` のとき環境変数 `FUSEJI_DETECT_INCLUDE_SURFACE`
            を参照し、それも未設定なら **False**（デフォルトで省略）。`True` で
            opt-in した場合も高センシティビティ type
            (`MY_NUMBER` / `CREDIT_CARD` / `CORPORATE_NUMBER`) は `<redacted>`
            固定。「detect, never retain」 / OWASP LLM02:2025 / CWE-200 対応。

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
    actual_api_key: str | None = api_key if api_key is not None else _api_key_from_env()
    actual_cors_origins: list[str] | None
    if cors_origins is not None:
        actual_cors_origins = list(cors_origins)
    else:
        actual_cors_origins = _cors_origins_from_env()
    actual_detect_include_surface: bool = (
        detect_include_surface
        if detect_include_surface is not None
        else _detect_include_surface_from_env()
    )

    new_app = FastAPI(
        title="fuseji",
        description="日本語特化の PII 検出・マスキングミドルウェア",
        version=__version__,
    )
    # ミドルウェアは登録順の逆順で外側に被さる。最外周から順に:
    # CORS（プリフライト処理）→ timeout → body-size → auth → アプリ
    # 認証より外側に CORS を置くことで、preflight (OPTIONS) は認証なしで通る。
    new_app.add_middleware(BodySizeLimitMiddleware, max_bytes=actual_max_body)
    if actual_api_key is not None:
        new_app.add_middleware(ApiKeyAuthMiddleware, api_key=actual_api_key)
    new_app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=actual_timeout)
    if actual_cors_origins:
        new_app.add_middleware(
            CORSMiddleware,
            allow_origins=actual_cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-API-Key"],
        )

    @new_app.post("/mask", response_model=MaskResponse)
    def mask_endpoint(req: MaskRequest) -> MaskResponse:
        """JSON データを受け取り、マスク済みの同型データを返す。"""
        return MaskResponse(data=actual_masker.mask_json(req.data))

    @new_app.post("/detect", response_model=DetectResponse)
    def detect_endpoint(req: DetectRequest) -> DetectResponse:
        """テキストから PII を検出して entity 一覧を返す。

        デフォルトで原 PII surface (`text`) はレスポンスに含めない (#143)。
        `detect_include_surface=True` を opt-in したときのみ含めるが、
        高センシティビティ type は `<redacted>` で固定マスクする。
        """
        entities = actual_masker.detect(req.text)
        return DetectResponse(
            entities=[
                EntityModel(
                    type=e.type,
                    text=_resolve_detect_text(e.type, e.text, actual_detect_include_surface),
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
