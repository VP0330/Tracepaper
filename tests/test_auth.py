"""Invite-only account and session lifecycle tests."""

import pytest

from tracepaper.auth import AuthService
from tracepaper.config import Settings


def test_bootstrap_invite_login_logout_lifecycle():
    service = AuthService(Settings(database_url="sqlite:///:memory:", cache_enabled=False))
    admin = service.bootstrap_admin("ADMIN@example.test", "Audit Admin", "a-long-admin-password")
    invite, raw_token = service.create_invite(
        "reviewer@example.test", "Reviewer", "reviewer", admin["user_id"],
    )

    assert invite["email"] == "reviewer@example.test"
    user = service.accept_invite(raw_token, "a-long-reviewer-password")
    assert user["role"] == "reviewer"
    with pytest.raises(ValueError, match="invalid, expired, or already used"):
        service.accept_invite(raw_token, "another-long-password")

    logged_in_user, session_token, expires_at = service.login(
        "REVIEWER@example.test", "a-long-reviewer-password",
    )
    assert logged_in_user["user_id"] == user["user_id"]
    assert expires_at > service.authenticate(session_token).created_at
    assert service.authenticate(session_token).user_id == user["user_id"]

    service.logout(session_token)
    assert service.authenticate(session_token) is None


def test_invites_reject_short_passwords_and_invalid_roles():
    service = AuthService(Settings(database_url="sqlite:///:memory:", cache_enabled=False))
    admin = service.bootstrap_admin("admin@example.test", "Admin", "a-long-admin-password")
    with pytest.raises(ValueError, match="Role must be admin or reviewer"):
        service.create_invite("x@example.test", "User", "owner", admin["user_id"])
    invite, raw_token = service.create_invite("x@example.test", "User", "reviewer", admin["user_id"])
    with pytest.raises(ValueError, match="at least 12 characters"):
        service.accept_invite(raw_token, "short")
