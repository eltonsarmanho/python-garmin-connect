"""
GenerateTokenGarmin.py — Authenticate with Garmin using email/password.

Based on:
  cyberjunky/python-garminconnect
  https://github.com/cyberjunky/python-garminconnect

Authenticates directly via the garminconnect library (no browser automation).
Tokens are persisted in ~/.garth for reuse across sessions.

Usage:
  python GenerateTokenGarmin.py
"""
import getpass
import sys
from pathlib import Path
from typing import Optional
from typing import Tuple

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_DIR = str(Path.home() / ".garth")


def prompt_credentials() -> Tuple[str, str]:
    """Prompt the user for Garmin credentials."""
    email = input("Email Garmin: ").strip()
    if not email:
        raise ValueError("Email é obrigatório.")
    password = getpass.getpass("Senha Garmin: ").strip()
    if not password:
        raise ValueError("Senha é obrigatória.")
    return email, password


def get_mfa_code() -> str:
    """Prompt for MFA/2FA verification code."""
    return input("Código de autenticação MFA: ").strip()


def _fresh_login(email: str, password: str) -> Garmin:
    """Authenticate with email/password, supporting MFA if required."""
    api = Garmin(email=email, password=password, is_cn=False, prompt_mfa=get_mfa_code)
    try:
        api.login()
    except GarminConnectAuthenticationError as err:
        print(f"\n[ERRO] Falha de autenticação: {err}", file=sys.stderr)
        sys.exit(1)
    except GarminConnectTooManyRequestsError as err:
        print(
            f"\n[ERRO] Muitas requisições (429). Aguarde alguns minutos e tente novamente.\n{err}",
            file=sys.stderr,
        )
        sys.exit(1)
    except GarminConnectConnectionError as err:
        print(f"\n[ERRO] Falha de conexão: {err}", file=sys.stderr)
        sys.exit(1)
    return api


def authenticate(email: str, password: str) -> Garmin:
    """
    Try to resume a session from saved tokens in TOKEN_DIR.
    Fall back to a fresh email/password login and save the new tokens.
    """
    try:
        api = Garmin()
        api.login(TOKEN_DIR)
        print("Sessão retomada a partir de tokens salvos.")
        return api
    except Exception:
        pass

    print("Nenhum token válido encontrado — autenticando com email/senha...")
    api = _fresh_login(email, password)
    Path(TOKEN_DIR).mkdir(parents=True, exist_ok=True)
    api.client.dump(TOKEN_DIR)
    print(f"Tokens salvos em: {TOKEN_DIR}")
    return api


def main():
    print("Garmin Connect — Autenticação por Email/Senha")
    print("=" * 50)

    email, password = prompt_credentials()

    print("\nAutenticando...")
    api = _fresh_login(email, password)

    print("Salvando tokens...")
    Path(TOKEN_DIR).mkdir(parents=True, exist_ok=True)
    api.client.dump(TOKEN_DIR)

    try:
        name = api.get_full_name()
        print(f"\nAutenticado como: {name}")
    except Exception:
        print("\nAutenticação bem-sucedida!")

    print(f"Tokens salvos em: {TOKEN_DIR}")
    print("\nExecute FetchGarminData.py para buscar seus dados Garmin.")


if __name__ == "__main__":
    main()
