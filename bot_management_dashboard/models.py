from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot_management_dashboard.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "dashboard_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    wallet_address: Mapped[str] = mapped_column(String(42), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    exchange_credentials: Mapped[list["ExchangeCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    telegram_config: Mapped["TelegramConfig | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    strategies: Mapped[list["StrategyConfig"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    runtime: Mapped["BotRuntime | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    metric: Mapped["DashboardMetric | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class AuthChallenge(Base):
    __tablename__ = "dashboard_auth_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet_address: Mapped[str] = mapped_column(String(42), index=True, nullable=False)
    nonce: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExchangeCredential(Base):
    __tablename__ = "dashboard_exchange_credentials"
    __table_args__ = (UniqueConstraint("user_id", "exchange_name", name="uq_user_exchange"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("dashboard_users.id", ondelete="CASCADE"), index=True)
    exchange_name: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_secret: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_passphrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="exchange_credentials")


class TelegramConfig(Base):
    __tablename__ = "dashboard_telegram_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dashboard_users.id", ondelete="CASCADE"), unique=True, index=True
    )
    encrypted_bot_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="telegram_config")


class StrategyConfig(Base):
    __tablename__ = "dashboard_strategies"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_strategy_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("dashboard_users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="strategies")


class BotRuntime(Base):
    __tablename__ = "dashboard_bot_runtime"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dashboard_users.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="stopped", nullable=False)
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("dashboard_strategies.id", ondelete="SET NULL"), nullable=True
    )
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="runtime")
    strategy: Mapped[StrategyConfig | None] = relationship()


class DashboardMetric(Base):
    __tablename__ = "dashboard_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("dashboard_users.id", ondelete="CASCADE"), unique=True, index=True
    )
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    open_positions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="metric")

