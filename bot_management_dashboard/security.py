from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet
from eth_account import Account
from eth_account.messages import encode_defunct

from bot_management_dashboard.config import DashboardSettings


JWT_ALGORITHM = "HS256"


class CryptoManager:
    def __init__(self, encryption_key: str) -> None:
        self._fernet = Fernet(encryption_key.encode("utf-8"))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")


def normalize_wallet_address(wallet_address: str) -> str:
    return wallet_address.lower().strip()


def generate_nonce() -> str:
    return secrets.token_urlsafe(24)


def build_signin_message(wallet_address: str, nonce: str, domain: str, issued_at: datetime) -> str:
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n"
        f"{wallet_address}\n\n"
        "Sign in to configure and run your trading bot securely.\n\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued_at.isoformat()}"
    )


def create_access_token(wallet_address: str, settings: DashboardSettings) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_exp_minutes)
    payload = {"sub": wallet_address, "exp": expires_at, "iat": datetime.now(UTC)}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str, settings: DashboardSettings) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    wallet_address = payload.get("sub")
    if not isinstance(wallet_address, str):
        raise jwt.InvalidTokenError("Missing wallet subject")
    return wallet_address


def verify_wallet_signature(message: str, signature: str, wallet_address: str) -> bool:
    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:
        return False
    return normalize_wallet_address(recovered) == normalize_wallet_address(wallet_address)


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def mask_chat_id(chat_id: str) -> str:
    if len(chat_id) <= 4:
        return "*" * len(chat_id)
    return f"{chat_id[:2]}{'*' * (len(chat_id) - 4)}{chat_id[-2:]}"

