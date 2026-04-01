from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from sqlalchemy import select

from bot_management_dashboard import database
from bot_management_dashboard.config import clear_settings_cache, get_settings
from bot_management_dashboard.database import Base, reset_database_engine
from bot_management_dashboard.models import ExchangeCredential
from bot_management_dashboard.security import CryptoManager


@pytest.fixture
def dashboard_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "dashboard_test.sqlite"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("DASHBOARD_DATABASE_URL", db_url)
    monkeypatch.setenv(
        "DASHBOARD_JWT_SECRET",
        "test-dashboard-jwt-secret-with-minimum-thirty-two-bytes",
    )
    monkeypatch.setenv("DASHBOARD_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    clear_settings_cache()

    reset_database_engine(db_url)

    from bot_management_dashboard import main as dashboard_main

    dashboard_main.settings = get_settings()
    dashboard_main.crypto = CryptoManager(dashboard_main.settings.encryption_key)
    dashboard_main._auth_requests.clear()

    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)

    with TestClient(dashboard_main.app) as client:
        yield client, dashboard_main


def _sign_in(client: TestClient) -> tuple[str, dict[str, str]]:
    account = Account.create()
    wallet_address = account.address

    challenge_response = client.post("/api/auth/challenge", json={"wallet_address": wallet_address})
    assert challenge_response.status_code == 200
    challenge = challenge_response.json()

    signed = Account.sign_message(encode_defunct(text=challenge["message"]), private_key=account.key)
    verify_response = client.post(
        "/api/auth/verify",
        json={
            "wallet_address": wallet_address,
            "nonce": challenge["nonce"],
            "message": challenge["message"],
            "signature": signed.signature.hex(),
        },
    )
    assert verify_response.status_code == 200

    token = verify_response.json()["access_token"]
    return wallet_address.lower(), {"Authorization": f"Bearer {token}"}


def test_auth_challenge_verify_and_profile(dashboard_client):
    client, _dashboard_main = dashboard_client
    wallet_address, headers = _sign_in(client)

    profile_response = client.get("/api/me", headers=headers)
    assert profile_response.status_code == 200
    assert profile_response.json()["wallet_address"] == wallet_address


def test_dev_login_flow(dashboard_client):
    client, _dashboard_main = dashboard_client
    wallet_address = "0x1111111111111111111111111111111111111111"

    login_response = client.post("/api/auth/dev-login", json={"wallet_address": wallet_address})
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    profile_response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert profile_response.status_code == 200
    assert profile_response.json()["wallet_address"] == wallet_address


def test_exchange_credentials_are_masked_and_encrypted(dashboard_client):
    client, dashboard_main = dashboard_client
    _wallet_address, headers = _sign_in(client)

    api_key = "ABCD1234LONGSECRETKEY"
    api_secret = "VERY_SECRET_EXCHANGE_SECRET"
    response = client.put(
        "/api/exchange-credentials",
        json={
            "exchange_name": "binance",
            "api_key": api_key,
            "api_secret": api_secret,
            "passphrase": "optional-passphrase",
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["exchange_name"] == "binance"
    assert payload["api_key_masked"] != api_key
    assert "ABCD" in payload["api_key_masked"]
    assert "KEY" in payload["api_key_masked"]

    list_response = client.get("/api/exchange-credentials", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["api_key_masked"] != api_key

    with database.SessionLocal() as db:
        credential = db.scalar(select(ExchangeCredential))
        assert credential is not None
        assert credential.encrypted_api_key != api_key
        assert credential.encrypted_api_secret != api_secret
        assert dashboard_main.crypto.decrypt(credential.encrypted_api_key) == api_key


def test_strategy_run_and_dashboard_flow(dashboard_client):
    client, _dashboard_main = dashboard_client
    _wallet_address, headers = _sign_in(client)

    strategy_response = client.post(
        "/api/strategies",
        json={
            "name": "mean-reversion",
            "parameters": {"timeframe": "5m", "stake_amount": 100, "max_open_trades": 2},
            "enabled": True,
        },
        headers=headers,
    )
    assert strategy_response.status_code == 200
    strategy_id = strategy_response.json()["id"]

    run_without_deps = client.post("/api/bot/run", json={"strategy_id": strategy_id}, headers=headers)
    assert run_without_deps.status_code == 400

    exchange_response = client.put(
        "/api/exchange-credentials",
        json={
            "exchange_name": "okx",
            "api_key": "KEY_123456789",
            "api_secret": "SECRET_123456789",
            "passphrase": None,
        },
        headers=headers,
    )
    assert exchange_response.status_code == 200

    telegram_response = client.put(
        "/api/telegram",
        json={"bot_token": "123456:telegram-token", "chat_id": "987654321"},
        headers=headers,
    )
    assert telegram_response.status_code == 200
    assert telegram_response.json()["chat_id_masked"] != "987654321"

    run_response = client.post("/api/bot/run", json={"strategy_id": strategy_id}, headers=headers)
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "running"

    overview_response = client.get("/api/dashboard/overview", headers=headers)
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["bot_status"] == "running"
    assert overview["strategy_count"] == 1
    assert overview["exchange_connections"] == 1
    assert overview["telegram_configured"] is True
    assert overview["active_strategy_id"] == strategy_id


def test_backtesting_comparison_tab_data(dashboard_client):
    client, _dashboard_main = dashboard_client
    _wallet_address, headers = _sign_in(client)

    strategy_a = client.post(
        "/api/strategies",
        json={
            "name": "trend-alpha",
            "parameters": {
                "template": "trend-follow",
                "timeframe": "5m",
                "max_open_trades": 3,
                "risk": {"level": "medium"},
                "signals": {"entry": "ema_cross"},
            },
            "enabled": True,
        },
        headers=headers,
    )
    strategy_b = client.post(
        "/api/strategies",
        json={
            "name": "reversion-beta",
            "parameters": {
                "template": "mean-reversion",
                "timeframe": "15m",
                "max_open_trades": 2,
                "risk": {"level": "low"},
                "signals": {"entry": "rsi_reversal"},
            },
            "enabled": True,
        },
        headers=headers,
    )
    assert strategy_a.status_code == 200
    assert strategy_b.status_code == 200

    response = client.post(
        "/api/backtesting/run",
        json={
            "strategy_ids": [strategy_a.json()["id"], strategy_b.json()["id"]],
            "timerange_days": 180,
            "initial_balance": 15000,
            "fee_pct": 0.1,
            "slippage_pct": 0.05,
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["timerange_days"] == 180
    assert payload["initial_balance"] == 15000
    assert len(payload["results"]) == 2
    assert payload["results"][0]["score"] >= payload["results"][1]["score"]
    assert payload["best_strategy_id"] in [strategy_a.json()["id"], strategy_b.json()["id"]]
    assert len(payload["results"][0]["equity_curve"]) == 12

