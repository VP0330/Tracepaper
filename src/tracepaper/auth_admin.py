"""Provision the first Tracepaper administrator."""

import getpass

from tracepaper.auth import AuthService
from tracepaper.config import get_settings


def main() -> None:
    settings = get_settings()
    service = AuthService(settings)
    email = input("Administrator email: ").strip()
    display_name = input("Display name: ").strip()
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    try:
        user = service.bootstrap_admin(email, display_name, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Created administrator account for {user['email']}.")


if __name__ == "__main__":
    main()
