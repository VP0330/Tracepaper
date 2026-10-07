"""Invite-only authentication backed by the configured SQL database."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from tracepaper.config import Settings
from tracepaper.storage.db import get_engine, get_session_factory, init_db
from tracepaper.storage.models import InviteRecord, SessionRecord, UserRecord


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        candidate = _password_hash(password, bytes.fromhex(salt_hex)).split("$", 2)[2]
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user: UserRecord) -> dict[str, str]:
    return {"user_id": user.user_id, "email": user.email, "display_name": user.display_name, "role": user.role}


class AuthService:
    def __init__(self, settings: Settings):
        self.engine = get_engine(settings.database_url)
        init_db(self.engine)
        self.session_factory = get_session_factory(self.engine)
        self.invite_expiry = timedelta(hours=settings.invite_expiry_hours)
        self.session_expiry = timedelta(hours=settings.session_expiry_hours)

    def bootstrap_admin(self, email: str, display_name: str, password: str) -> dict[str, str]:
        email = email.strip().casefold()
        with self.session_factory() as session:
            existing = session.scalar(select(UserRecord).where(UserRecord.email == email))
            if existing:
                raise ValueError("An account with this email already exists")
            user = UserRecord(
                user_id=str(uuid.uuid4()), email=email, display_name=display_name.strip(),
                password_hash=_password_hash(password), role="admin",
            )
            session.add(user)
            session.commit()
            return public_user(user)

    def create_invite(self, email: str, display_name: str, role: str, created_by: str) -> tuple[dict[str, str], str]:
        email = email.strip().casefold()
        if role not in {"admin", "reviewer"}:
            raise ValueError("Role must be admin or reviewer")
        raw_token = secrets.token_urlsafe(32)
        with self.session_factory() as session:
            if session.scalar(select(UserRecord).where(UserRecord.email == email)):
                raise ValueError("This email already has an account")
            invite = InviteRecord(
                invite_id=str(uuid.uuid4()), email=email, display_name=display_name.strip(), role=role,
                token_hash=_token_hash(raw_token), expires_at=datetime.utcnow() + self.invite_expiry,
                created_by=created_by,
            )
            session.add(invite)
            session.commit()
            return ({"invite_id": invite.invite_id, "email": email, "role": role,
                     "expires_at": invite.expires_at.isoformat()}, raw_token)

    def accept_invite(self, token: str, password: str) -> dict[str, str]:
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters")
        now = datetime.utcnow()
        with self.session_factory() as session:
            invite = session.scalar(select(InviteRecord).where(InviteRecord.token_hash == _token_hash(token)))
            if invite is None or invite.used_at is not None or invite.expires_at <= now:
                raise ValueError("Invitation is invalid, expired, or already used")
            user = UserRecord(
                user_id=str(uuid.uuid4()), email=invite.email, display_name=invite.display_name,
                password_hash=_password_hash(password), role=invite.role,
            )
            session.add(user)
            invite.used_at = now
            session.commit()
            return public_user(user)

    def login(self, email: str, password: str) -> tuple[dict[str, str], str, datetime]:
        now = datetime.utcnow()
        with self.session_factory() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.email == email.strip().casefold()))
            if user is None or not _verify_password(password, user.password_hash):
                raise ValueError("Invalid email or password")
            raw_token = secrets.token_urlsafe(40)
            expires_at = now + self.session_expiry
            session.add(SessionRecord(
                session_id=str(uuid.uuid4()), user_id=user.user_id,
                token_hash=_token_hash(raw_token), expires_at=expires_at,
            ))
            session.commit()
            return public_user(user), raw_token, expires_at

    def authenticate(self, token: str) -> UserRecord | None:
        now = datetime.utcnow()
        with self.session_factory() as session:
            record = session.scalar(select(SessionRecord).where(
                SessionRecord.token_hash == _token_hash(token), SessionRecord.expires_at > now,
            ))
            if record is None:
                return None
            user: UserRecord | None = session.get(UserRecord, record.user_id)
            if user:
                session.expunge(user)
            return user

    def logout(self, token: str) -> None:
        with self.session_factory() as session:
            record = session.scalar(select(SessionRecord).where(SessionRecord.token_hash == _token_hash(token)))
            if record:
                session.delete(record)
                session.commit()
