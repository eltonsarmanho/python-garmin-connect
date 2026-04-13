"""
FetchGarminData.py
------------------
Fetch Garmin Connect data using email/password authentication.

Flow:
1. Ask the user for Garmin email and password.
2. Try to resume a saved session from ~/.garth; fall back to fresh login.
3. Fetch and display: profile, daily summary, recent activities,
   heart rate, and sleep data.

Usage:
  python FetchGarminData.py
"""

import getpass
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

TOKEN_DIR = str(Path.home() / ".garth")


# ── Authentication ────────────────────────────────────────────────────────────

def prompt_credentials() -> tuple[str, str]:
    email = input("Email Garmin: ").strip()
    if not email:
        raise ValueError("Email é obrigatório.")
    password = getpass.getpass("Senha Garmin: ").strip()
    if not password:
        raise ValueError("Senha é obrigatória.")
    return email, password


def get_mfa_code() -> str:
    return input("Código MFA: ").strip()


def authenticate(email: str, password: str) -> Garmin:
    """Load saved tokens from ~/.garth or perform a fresh login."""
    try:
        api = Garmin()
        api.login(TOKEN_DIR)
        print("Sessão retomada a partir de tokens salvos.")
        return api
    except Exception:
        pass

    print("Autenticando com email/senha...")
    api = Garmin(email=email, password=password, is_cn=False, prompt_mfa=get_mfa_code)
    try:
        api.login()
    except GarminConnectAuthenticationError as err:
        print(f"[ERRO] Autenticação falhou: {err}", file=sys.stderr)
        sys.exit(1)
    except GarminConnectTooManyRequestsError:
        print("[ERRO] Muitas requisições (429). Tente novamente mais tarde.", file=sys.stderr)
        sys.exit(1)
    except GarminConnectConnectionError as err:
        print(f"[ERRO] Falha de conexão: {err}", file=sys.stderr)
        sys.exit(1)

    Path(TOKEN_DIR).mkdir(parents=True, exist_ok=True)
    api.client.dump(TOKEN_DIR)
    return api


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_fetch(fetcher, *args, default=None):
    try:
        return fetcher(*args)
    except Exception as exc:
        return {"error": str(exc)} if default is None else default


def format_hr(value) -> str:
    return f"{value} bpm" if value is not None else "N/A"


def format_seconds_as_hm(value) -> str:
    if value is None:
        return "N/A"
    hours, remainder = divmod(int(value), 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes:02d}m"


def format_seconds_as_minutes(value) -> str:
    if value is None:
        return "N/A"
    return f"{int(value) // 60} min"


def print_header(title: str) -> None:
    print("─" * 10)
    print(title)
    print("─" * 10)


# ── Display ───────────────────────────────────────────────────────────────────

def print_dashboard(api: Garmin, today: str, yesterday: str) -> None:
    # ── Profile ──────────────────────────────────────────────────────────────
    print_header("PERFIL")
    full_name = safe_fetch(api.get_full_name, default="N/A")
    print(f"  Nome: {full_name}")

    # ── Daily summary ─────────────────────────────────────────────────────────
    print()
    print_header(f"RESUMO DO DIA ({today})")
    summary = safe_fetch(api.get_stats, today)
    if summary and "error" not in summary:
        def fv(v, unit=""):
            return f"{v}{unit}" if v is not None else "N/A"

        dist_m = summary.get("totalDistanceMeters")
        print(f"  Total kcal  : {fv(summary.get('totalKilocalories'), ' kcal')}")
        print(f"  Ativas      : {fv(summary.get('activeKilocalories'), ' kcal')}")
        print(f"  BMR         : {fv(summary.get('bmrKilocalories'), ' kcal')}")
        print(f"  Passos      : {fv(summary.get('totalSteps'))}")
        print(f"  Distância   : {f'{dist_m / 1000:.2f} km' if dist_m is not None else 'N/A'}")
        print(f"  Andares     : {fv(summary.get('floorsAscended'))}")
    else:
        err = summary.get("error") if summary else "sem dados"
        print(f"  (não disponível: {err})")

    # ── Recent activities ─────────────────────────────────────────────────────
    print()
    print_header("ATIVIDADES RECENTES (últimas 5)")
    activities = safe_fetch(api.get_activities, 0, 5, default=[])
    if not activities:
        print("  Nenhuma atividade encontrada.")
    else:
        for act in activities:
            name = act.get("activityName", "?")
            sport = act.get("activityType", {}).get("typeKey", "?")
            dist = (act.get("distance") or 0) / 1000
            calories = act.get("calories") or 0
            dur = int(act.get("duration") or 0)
            start_t = act.get("startTimeLocal", "?")
            print(
                f"  [{start_t}]  {sport:20s}  {dist:.2f} km  "
                f"{dur // 60}m{dur % 60:02d}s  {int(calories)} kcal  \"{name}\""
            )

    # ── Heart rate ────────────────────────────────────────────────────────────
    print()
    print_header(f"FREQUÊNCIA CARDÍACA ({yesterday})")
    hr = safe_fetch(api.get_heart_rates, yesterday)
    if hr and "error" not in hr:
        print(f"  Repouso : {format_hr(hr.get('restingHeartRate'))}")
        print(f"  Mínima  : {format_hr(hr.get('minHeartRate'))}")
        print(f"  Máxima  : {format_hr(hr.get('maxHeartRate'))}")
    else:
        err = hr.get("error") if hr else "sem dados"
        print(f"  (não disponível: {err})")

    # ── Sleep ─────────────────────────────────────────────────────────────────
    print()
    print_header(f"SONO ({yesterday})")
    sleep = safe_fetch(api.get_sleep_data, yesterday)
    if sleep and "error" not in sleep:
        daily_sleep = sleep.get("dailySleepDTO") or {}
        print(f"  Total    : {format_seconds_as_hm(daily_sleep.get('sleepTimeSeconds'))}")
        print(f"  Profundo : {format_seconds_as_minutes(daily_sleep.get('deepSleepSeconds'))}")
        print(f"  Leve     : {format_seconds_as_minutes(daily_sleep.get('lightSleepSeconds'))}")
        print(f"  REM      : {format_seconds_as_minutes(daily_sleep.get('remSleepSeconds'))}")
        print(f"  Acordado : {format_seconds_as_minutes(daily_sleep.get('awakeSleepSeconds'))}")
    else:
        err = sleep.get("error") if sleep else "sem dados"
        print(f"  (não disponível: {err})")

    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    email, password = prompt_credentials()

    print("\nConectando ao Garmin Connect...")
    api = authenticate(email, password)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    print_dashboard(api, today, yesterday)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
