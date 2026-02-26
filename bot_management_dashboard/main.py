from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from bot_management_dashboard import database
from bot_management_dashboard.auth import get_current_user
from bot_management_dashboard.config import get_settings
from bot_management_dashboard.database import Base, get_db
from bot_management_dashboard.models import (
    AuthChallenge,
    BotRuntime,
    DashboardMetric,
    ExchangeCredential,
    StrategyConfig,
    TelegramConfig,
    User,
)
from bot_management_dashboard.schemas import (
    AuthChallengeRequest,
    AuthChallengeResponse,
    AuthVerifyRequest,
    BotRunRequest,
    BotStatusResponse,
    DashboardMetricsResponse,
    DashboardOverviewResponse,
    DevLoginRequest,
    ExchangeCredentialResponse,
    ExchangeCredentialUpsert,
    StatusResponse,
    StrategyResponse,
    StrategyUpsert,
    TelegramConfigResponse,
    TelegramConfigUpsert,
    TokenResponse,
    UserProfileResponse,
)
from bot_management_dashboard.security import (
    CryptoManager,
    build_signin_message,
    create_access_token,
    generate_nonce,
    mask_chat_id,
    mask_secret,
    normalize_wallet_address,
    verify_wallet_signature,
)


settings = get_settings()
crypto = CryptoManager(settings.encryption_key)
_auth_requests: dict[str, deque[datetime]] = defaultdict(deque)

app = FastAPI(
    title="Bot Management Dashboard",
    description="Secure MetaMask-authenticated dashboard for configuring and running trading bots.",
    version="0.1.0",
)


if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def _rate_limit_auth(request: Request) -> None:
    now = datetime.now(UTC)
    client_ip = _get_client_ip(request)
    attempts = _auth_requests[client_ip]
    window = timedelta(seconds=settings.auth_rate_window_seconds)
    while attempts and now - attempts[0] > window:
        attempts.popleft()
    if len(attempts) >= settings.auth_rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many auth attempts. Please retry shortly.",
        )
    attempts.append(now)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _ensure_runtime(db: Session, user_id: int) -> BotRuntime:
    runtime = db.scalar(select(BotRuntime).where(BotRuntime.user_id == user_id))
    if runtime is None:
        runtime = BotRuntime(user_id=user_id, status="stopped")
        db.add(runtime)
        db.flush()
    return runtime


def _ensure_metric(db: Session, user_id: int) -> DashboardMetric:
    metric = db.scalar(select(DashboardMetric).where(DashboardMetric.user_id == user_id))
    if metric is None:
        metric = DashboardMetric(user_id=user_id)
        db.add(metric)
        db.flush()
    return metric


def _credential_to_response(record: ExchangeCredential) -> ExchangeCredentialResponse:
    api_key = crypto.decrypt(record.encrypted_api_key)
    return ExchangeCredentialResponse(
        exchange_name=record.exchange_name,
        api_key_masked=mask_secret(api_key),
        has_passphrase=bool(record.encrypted_passphrase),
        updated_at=record.updated_at,
    )


def _telegram_to_response(record: TelegramConfig) -> TelegramConfigResponse:
    chat_id = crypto.decrypt(record.encrypted_chat_id)
    return TelegramConfigResponse(
        chat_id_masked=mask_chat_id(chat_id),
        has_bot_token=True,
        updated_at=record.updated_at,
    )


def _runtime_to_response(runtime: BotRuntime) -> BotStatusResponse:
    return BotStatusResponse(
        status=runtime.status,
        strategy_id=runtime.strategy_id,
        last_started_at=runtime.last_started_at,
        last_stopped_at=runtime.last_stopped_at,
        updated_at=runtime.updated_at,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "script-src 'self' https://esm.sh; "
        "style-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'"
    )
    return response


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=database.engine)


@app.get("/health", response_model=StatusResponse, tags=["Health"])
def health() -> StatusResponse:
    return StatusResponse(status="ok", message="dashboard service online")


@app.post("/api/auth/challenge", response_model=AuthChallengeResponse, tags=["Auth"])
def auth_challenge(
    payload: AuthChallengeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthChallengeResponse:
    _rate_limit_auth(request)
    wallet_address = normalize_wallet_address(payload.wallet_address)
    issued_at = datetime.now(UTC)
    nonce = generate_nonce()
    expires_at = issued_at + timedelta(seconds=settings.nonce_ttl_seconds)
    message = build_signin_message(wallet_address, nonce, settings.allowed_domain, issued_at)

    db.execute(delete(AuthChallenge).where(AuthChallenge.wallet_address == wallet_address))
    db.add(
        AuthChallenge(
            wallet_address=wallet_address,
            nonce=nonce,
            message=message,
            expires_at=expires_at,
        )
    )
    db.commit()
    return AuthChallengeResponse(nonce=nonce, message=message, expires_at=expires_at)


@app.post("/api/auth/verify", response_model=TokenResponse, tags=["Auth"])
def auth_verify(
    payload: AuthVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    _rate_limit_auth(request)
    wallet_address = normalize_wallet_address(payload.wallet_address)
    challenge = db.scalar(
        select(AuthChallenge).where(
            AuthChallenge.wallet_address == wallet_address,
            AuthChallenge.nonce == payload.nonce,
            AuthChallenge.consumed_at.is_(None),
        )
    )
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Challenge not found.")
    if _as_utc(challenge.expires_at) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Challenge expired.")
    if payload.message != challenge.message:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Challenge mismatch.")
    if not verify_wallet_signature(payload.message, payload.signature, wallet_address):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature.")

    user = db.scalar(select(User).where(User.wallet_address == wallet_address))
    if user is None:
        user = User(wallet_address=wallet_address)
        db.add(user)
        db.flush()
    _ensure_runtime(db, user.id)
    _ensure_metric(db, user.id)

    challenge.consumed_at = datetime.now(UTC)
    access_token, expires_at = create_access_token(wallet_address, settings)
    db.commit()
    return TokenResponse(access_token=access_token, expires_at=expires_at)


@app.post("/api/auth/dev-login", response_model=TokenResponse, tags=["Auth"])
def auth_dev_login(payload: DevLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    wallet_address = normalize_wallet_address(payload.wallet_address)
    user = db.scalar(select(User).where(User.wallet_address == wallet_address))
    if user is None:
        user = User(wallet_address=wallet_address)
        db.add(user)
        db.flush()
    _ensure_runtime(db, user.id)
    _ensure_metric(db, user.id)

    access_token, expires_at = create_access_token(wallet_address, settings)
    db.commit()
    return TokenResponse(access_token=access_token, expires_at=expires_at)


@app.get("/api/me", response_model=UserProfileResponse, tags=["User"])
def get_profile(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    return UserProfileResponse(
        wallet_address=current_user.wallet_address,
        created_at=current_user.created_at,
    )


@app.put(
    "/api/exchange-credentials",
    response_model=ExchangeCredentialResponse,
    tags=["Exchange"],
)
def upsert_exchange_credential(
    payload: ExchangeCredentialUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExchangeCredentialResponse:
    exchange_name = payload.exchange_name.strip().lower()
    record = db.scalar(
        select(ExchangeCredential).where(
            ExchangeCredential.user_id == current_user.id,
            ExchangeCredential.exchange_name == exchange_name,
        )
    )
    if record is None:
        record = ExchangeCredential(user_id=current_user.id, exchange_name=exchange_name)
        db.add(record)

    record.encrypted_api_key = crypto.encrypt(payload.api_key)
    record.encrypted_api_secret = crypto.encrypt(payload.api_secret)
    record.encrypted_passphrase = crypto.encrypt(payload.passphrase) if payload.passphrase else None
    db.commit()
    db.refresh(record)
    return _credential_to_response(record)


@app.get(
    "/api/exchange-credentials",
    response_model=list[ExchangeCredentialResponse],
    tags=["Exchange"],
)
def list_exchange_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ExchangeCredentialResponse]:
    records = db.scalars(
        select(ExchangeCredential)
        .where(ExchangeCredential.user_id == current_user.id)
        .order_by(ExchangeCredential.updated_at.desc())
    ).all()
    return [_credential_to_response(record) for record in records]


@app.put("/api/telegram", response_model=TelegramConfigResponse, tags=["Telegram"])
def upsert_telegram_config(
    payload: TelegramConfigUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TelegramConfigResponse:
    record = db.scalar(select(TelegramConfig).where(TelegramConfig.user_id == current_user.id))
    if record is None:
        record = TelegramConfig(user_id=current_user.id)
        db.add(record)

    record.encrypted_bot_token = crypto.encrypt(payload.bot_token)
    record.encrypted_chat_id = crypto.encrypt(payload.chat_id)
    db.commit()
    db.refresh(record)
    return _telegram_to_response(record)


@app.get("/api/telegram", response_model=TelegramConfigResponse, tags=["Telegram"])
def get_telegram_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TelegramConfigResponse:
    record = db.scalar(select(TelegramConfig).where(TelegramConfig.user_id == current_user.id))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram config not found.")
    return _telegram_to_response(record)


@app.post("/api/strategies", response_model=StrategyResponse, tags=["Strategy"])
def upsert_strategy(
    payload: StrategyUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyResponse:
    strategy_name = payload.name.strip()
    record = db.scalar(
        select(StrategyConfig).where(
            StrategyConfig.user_id == current_user.id,
            StrategyConfig.name == strategy_name,
        )
    )
    if record is None:
        record = StrategyConfig(user_id=current_user.id, name=strategy_name)
        db.add(record)

    record.parameters = payload.parameters
    record.enabled = payload.enabled
    db.commit()
    db.refresh(record)
    return StrategyResponse.model_validate(record)


@app.get("/api/strategies", response_model=list[StrategyResponse], tags=["Strategy"])
def list_strategies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StrategyResponse]:
    records = db.scalars(
        select(StrategyConfig)
        .where(StrategyConfig.user_id == current_user.id)
        .order_by(StrategyConfig.updated_at.desc())
    ).all()
    return [StrategyResponse.model_validate(record) for record in records]


@app.get("/api/bot/status", response_model=BotStatusResponse, tags=["Bot"])
def get_bot_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BotStatusResponse:
    runtime = _ensure_runtime(db, current_user.id)
    db.commit()
    db.refresh(runtime)
    return _runtime_to_response(runtime)


@app.post("/api/bot/run", response_model=BotStatusResponse, tags=["Bot"])
def run_bot(
    payload: BotRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BotStatusResponse:
    strategy = db.scalar(
        select(StrategyConfig).where(
            StrategyConfig.id == payload.strategy_id,
            StrategyConfig.user_id == current_user.id,
            StrategyConfig.enabled.is_(True),
        )
    )
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found or disabled.")
    has_exchange = db.scalar(
        select(func.count()).select_from(ExchangeCredential).where(ExchangeCredential.user_id == current_user.id)
    )
    if not has_exchange:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configure exchange credentials before starting the bot.",
        )
    telegram = db.scalar(select(TelegramConfig).where(TelegramConfig.user_id == current_user.id))
    if telegram is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configure Telegram before starting the bot.",
        )

    runtime = _ensure_runtime(db, current_user.id)
    _ensure_metric(db, current_user.id)
    runtime.status = "running"
    runtime.strategy_id = strategy.id
    runtime.last_started_at = datetime.now(UTC)
    runtime.last_error = None
    db.commit()
    db.refresh(runtime)
    return _runtime_to_response(runtime)


@app.post("/api/bot/stop", response_model=BotStatusResponse, tags=["Bot"])
def stop_bot(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BotStatusResponse:
    runtime = _ensure_runtime(db, current_user.id)
    runtime.status = "stopped"
    runtime.last_stopped_at = datetime.now(UTC)
    db.commit()
    db.refresh(runtime)
    return _runtime_to_response(runtime)


@app.get("/api/dashboard/overview", response_model=DashboardOverviewResponse, tags=["Dashboard"])
def dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardOverviewResponse:
    runtime = _ensure_runtime(db, current_user.id)
    metric = _ensure_metric(db, current_user.id)

    strategy_count = db.scalar(
        select(func.count()).select_from(StrategyConfig).where(StrategyConfig.user_id == current_user.id)
    )
    exchange_connections = db.scalar(
        select(func.count()).select_from(ExchangeCredential).where(ExchangeCredential.user_id == current_user.id)
    )
    telegram = db.scalar(select(TelegramConfig).where(TelegramConfig.user_id == current_user.id))

    db.commit()
    db.refresh(runtime)
    db.refresh(metric)

    return DashboardOverviewResponse(
        wallet_address=current_user.wallet_address,
        bot_status=runtime.status,
        strategy_count=strategy_count or 0,
        exchange_connections=exchange_connections or 0,
        telegram_configured=telegram is not None,
        active_strategy_id=runtime.strategy_id,
        metrics=DashboardMetricsResponse(
            total_pnl=metric.total_pnl,
            open_positions=metric.open_positions,
            total_trades=metric.total_trades,
            win_rate=metric.win_rate,
            max_drawdown=metric.max_drawdown,
            updated_at=metric.updated_at,
        ),
    )


app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/{rest_of_path:path}", include_in_schema=False)
def spa_fallback(rest_of_path: str):
    if rest_of_path.startswith("api"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    static_dir = settings.static_dir.resolve()
    candidate = (static_dir / rest_of_path).resolve()
    if candidate.is_file() and candidate.is_relative_to(static_dir):
        return FileResponse(candidate)
    return FileResponse(Path(settings.static_dir) / "index.html")

