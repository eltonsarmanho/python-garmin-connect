"""
FetchGarminData.py
------------------
Interactive Garmin data service.

Flow:
1. Ask the user for Garmin email and password.
2. Generate an OAuth token bundle using the Playwright flow from GenerateTokenGarmin.py.
3. Use the generated token in-memory to fetch profile, activities, heart rate, sleep,
   and daily summary data.

This script does not read GARTH_TOKEN from .env.
"""

from datetime import date, timedelta
from typing import Optional

import requests

from GenerateTokenGarmin import generate_token_bundle
from GenerateTokenGarmin import prompt_credentials

BASE = "https://connectapi.garmin.com"
HEADERS_TEMPLATE = {
    "User-Agent": "GCM-iOS-5.7.2.1",
    "NK": "NT",
    "origin": "https://connect.garmin.com",
}


def make_session(oauth2: dict) -> requests.Session:
    sess = requests.Session()
    sess.headers.update(HEADERS_TEMPLATE)
    sess.headers["Authorization"] = f"Bearer {oauth2['access_token']}"
    return sess


def get_profile(sess: requests.Session) -> dict:
    """Logged-in user profile."""
    r = sess.get(f"{BASE}/userprofile-service/socialProfile", timeout=15)
    r.raise_for_status()
    return r.json()


def get_activities(sess: requests.Session, start: int = 0, limit: int = 10) -> list:
    """Most recent activities."""
    r = sess.get(
        f"{BASE}/activitylist-service/activities/search/activities",
        params={"start": start, "limit": limit},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_daily_sleep(sess: requests.Session, sleep_date: str) -> dict:
    """Sleep data for a given date (YYYY-MM-DD)."""
    r = sess.get(
        f"{BASE}/wellness-service/wellness/dailySleepData",
        params={"date": sleep_date},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_heart_rate(sess: requests.Session, hr_date: str) -> dict:
    """Heart-rate summary for a given date (YYYY-MM-DD)."""
    r = sess.get(
        f"{BASE}/wellness-service/wellness/dailyHeartRate",
        params={"date": hr_date},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_daily_summary(sess: requests.Session, display_name: str, summary_date: str) -> dict:
    """Daily wellness summary: total/active/BMR calories, steps, distance, floors."""
    r = sess.get(
        f"{BASE}/usersummary-service/usersummary/daily/{display_name}",
        params={"calendarDate": summary_date},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


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


class GarminDataService:
    """Authenticate on demand and fetch Garmin data for the current session."""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.token_bundle: Optional[dict] = None
        self.session: Optional[requests.Session] = None
        self.profile: Optional[dict] = None

    def authenticate(self) -> dict:
        """Generate a token bundle and prepare the authenticated session."""
        print("Gerando token Garmin para esta sessao...")
        bundle, profile = generate_token_bundle(
            username=self.email,
            password=self.password,
            save_local_copy=False,
            verify=True,
        )
        self.token_bundle = bundle
        self.session = make_session(bundle["oauth2"])
        self.profile = profile or get_profile(self.session)
        return self.profile

    def ensure_authenticated(self) -> None:
        if self.session is None or self.profile is None:
            self.authenticate()

    def fetch_dashboard(self) -> dict:
        """Fetch the main Garmin dashboard payload."""
        self.ensure_authenticated()

        assert self.session is not None
        assert self.profile is not None

        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        display_name = self.profile.get("displayName", "")

        return {
            "profile": self.profile,
            "recent_activities": safe_fetch(get_activities, self.session, 0, 5, default=[]),
            "heart_rate": safe_fetch(get_heart_rate, self.session, yesterday),
            "sleep": safe_fetch(get_daily_sleep, self.session, yesterday),
            "daily_summary": safe_fetch(get_daily_summary, self.session, display_name, today),
            "today": today,
            "yesterday": yesterday,
        }


def print_dashboard(data: dict) -> None:
    profile = data["profile"]
    display_name = profile.get("displayName", "")

    print_header("PROFILE")
    print(f"  Name        : {profile.get('fullName', 'N/A')}")
    print(f"  Display name: {display_name}")
    print(f"  Location    : {profile.get('location', 'N/A')}")

    print()
    print_header("RECENT ACTIVITIES (last 5)")
    activities = data["recent_activities"]
    if not activities:
        print("  Nenhuma atividade encontrada.")
    for act in activities:
        name = act.get("activityName", "?")
        sport = act.get("activityType", {}).get("typeKey", "?")
        dist = act.get("distance", 0) / 1000
        calories = act.get("calories") or 0
        dur = int(act.get("duration", 0))
        start_t = act.get("startTimeLocal", "?")
        print(
            f"  [{start_t}]  {sport:20s}  {dist:.2f} km  "
            f"{dur//60}m{dur%60:02d}s  {int(calories)} kcal  \"{name}\""
        )

    print()
    print_header(f"HEART RATE ({data['yesterday']})")
    hr = data["heart_rate"]
    if "error" in hr:
        print(f"  (not available: {hr['error']})")
    else:
        print(f"  Resting HR : {format_hr(hr.get('restingHeartRate'))}")
        print(f"  Min HR     : {format_hr(hr.get('minHeartRate'))}")
        print(f"  Max HR     : {format_hr(hr.get('maxHeartRate'))}")

    print()
    print_header(f"SLEEP ({data['yesterday']})")
    sleep = data["sleep"]
    if "error" in sleep:
        print(f"  (not available: {sleep['error']})")
    else:
        daily_sleep = sleep.get("dailySleepDTO") or {}
        print(f"  Total sleep : {format_seconds_as_hm(daily_sleep.get('sleepTimeSeconds'))}")
        print(f"  Deep sleep  : {format_seconds_as_minutes(daily_sleep.get('deepSleepSeconds'))}")
        print(f"  Light sleep : {format_seconds_as_minutes(daily_sleep.get('lightSleepSeconds'))}")
        print(f"  REM sleep   : {format_seconds_as_minutes(daily_sleep.get('remSleepSeconds'))}")
        print(f"  Awake       : {format_seconds_as_minutes(daily_sleep.get('awakeSleepSeconds'))}")

    print()
    print_header(f"CALORIAS DO DIA ({data['today']})")
    summary = data["daily_summary"]
    if "error" in summary:
        print(f"  (not available: {summary['error']})")
    else:
        total = summary.get("totalKilocalories")
        active = summary.get("activeKilocalories")
        bmr = summary.get("bmrKilocalories")
        steps = summary.get("totalSteps")
        dist_m = summary.get("totalDistanceMeters")
        floors = summary.get("floorsAscended")

        def fv(value, unit=""):
            return f"{value}{unit}" if value is not None else "N/A"

        print(f"  Total kcal  : {fv(total, ' kcal')}")
        print(f"  Ativas      : {fv(active, ' kcal')}")
        print(f"  BMR         : {fv(bmr, ' kcal')}")
        print(f"  Passos      : {fv(steps)}")
        print(f"  Distancia   : {f'{dist_m/1000:.2f} km' if dist_m is not None else 'N/A'}")
        print(f"  Andares     : {fv(floors)}")

    print()


def main():
    email, password = prompt_credentials()
    service = GarminDataService(email=email, password=password)
    dashboard = service.fetch_dashboard()
    print_dashboard(dashboard)


if __name__ == "__main__":
    main()
