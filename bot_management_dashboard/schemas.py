from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


_WALLET_PATTERN = r"^0x[a-fA-F0-9]{40}$"


class AuthChallengeRequest(BaseModel):
    wallet_address: str = Field(pattern=_WALLET_PATTERN)


class AuthChallengeResponse(BaseModel):
    nonce: str
    message: str
    expires_at: datetime


class AuthVerifyRequest(BaseModel):
    wallet_address: str = Field(pattern=_WALLET_PATTERN)
    nonce: str = Field(min_length=8, max_length=120)
    message: str = Field(min_length=8, max_length=4096)
    signature: str = Field(min_length=60, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class DevLoginRequest(BaseModel):
    wallet_address: str = Field(default="0x1111111111111111111111111111111111111111", pattern=_WALLET_PATTERN)


class UserProfileResponse(BaseModel):
    wallet_address: str
    created_at: datetime


class ExchangeCredentialUpsert(BaseModel):
    exchange_name: str = Field(min_length=2, max_length=50)
    api_key: str = Field(min_length=3, max_length=256)
    api_secret: str = Field(min_length=3, max_length=256)
    passphrase: str | None = Field(default=None, max_length=256)


class ExchangeCredentialResponse(BaseModel):
    exchange_name: str
    api_key_masked: str
    has_passphrase: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TelegramConfigUpsert(BaseModel):
    bot_token: str = Field(min_length=10, max_length=256)
    chat_id: str = Field(min_length=2, max_length=64)


class TelegramConfigResponse(BaseModel):
    chat_id_masked: str
    has_bot_token: bool
    updated_at: datetime


class StrategyUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class StrategyResponse(BaseModel):
    id: int
    name: str
    parameters: dict[str, Any]
    enabled: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BacktestRunRequest(BaseModel):
    strategy_ids: list[int] = Field(min_length=1, max_length=20)
    timerange_days: int = Field(default=90, ge=7, le=3650)
    initial_balance: float = Field(default=10000.0, gt=0)
    fee_pct: float = Field(default=0.1, ge=0, le=5)
    slippage_pct: float = Field(default=0.05, ge=0, le=5)


class BacktestStrategyResult(BaseModel):
    strategy_id: int
    strategy_name: str
    total_trades: int
    win_rate: float
    max_drawdown: float
    total_return_pct: float
    net_profit: float
    sharpe: float
    score: float
    equity_curve: list[float]


class BacktestRunResponse(BaseModel):
    generated_at: datetime
    timerange_days: int
    initial_balance: float
    best_strategy_id: int
    results: list[BacktestStrategyResult]


class BotRunRequest(BaseModel):
    strategy_id: int = Field(ge=1)


class BotStatusResponse(BaseModel):
    status: str
    strategy_id: int | None
    last_started_at: datetime | None
    last_stopped_at: datetime | None
    updated_at: datetime


class DashboardMetricsResponse(BaseModel):
    total_pnl: float
    open_positions: int
    total_trades: int
    win_rate: float
    max_drawdown: float
    updated_at: datetime


class DashboardOverviewResponse(BaseModel):
    wallet_address: str
    bot_status: str
    strategy_count: int
    exchange_connections: int
    telegram_configured: bool
    active_strategy_id: int | None
    metrics: DashboardMetricsResponse


class StatusResponse(BaseModel):
    status: str
    message: str

