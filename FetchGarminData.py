"""
Fetches data from Garmin Connect using the token stored in .env (GARTH_TOKEN).
The token bundle is a base64-encoded JSON array: [oauth1_dict, oauth2_dict]
"""

import base64
import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://connectapi.garmin.com"
HEADERS_TEMPLATE = {
    "User-Agent": "GCM-iOS-5.7.2.1",
    "NK": "NT",
    "origin": "https://connect.garmin.com",
}


def load_token() -> dict:
    """Load and decode the OAuth2 token from GARTH_TOKEN env var."""
    raw = os.environ.get("GARTH_TOKEN")
    if not raw:
        raise RuntimeError("GARTH_TOKEN not found in .env")

    decoded = json.loads(base64.b64decode(raw).decode())

    # Bundle can be a list [oauth1, oauth2] or a dict {"oauth1":..., "oauth2":...}
    if isinstance(decoded, list):
        oauth2 = decoded[1]
    else:
        oauth2 = decoded["oauth2"]

    return oauth2


def make_session(oauth2: dict) -> requests.Session:
    sess = requests.Session()
    sess.headers.update(HEADERS_TEMPLATE)
    sess.headers["Authorization"] = f"Bearer {oauth2['access_token']}"
    return sess


# ─── API helpers ────────────────────────────────────────────────────────────

def get_profile(sess: requests.Session) -> dict:
    """Logged-in user profile."""
    r = sess.get(f"{BASE}/userprofile-service/socialProfile", timeout=15)
    r.raise_for_status()
    return r.json()


def get_user_stats(sess: requests.Session, display_name: str, stats_date: str) -> dict:
    """Daily summary stats (steps, calories, distance, active minutes…)."""
    r = sess.get(
        f"{BASE}/userstats-service/stats/{display_name}",
        params={"fromDate": stats_date, "untilDate": stats_date, "metricId": 60},
        timeout=15,
    )
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


def get_steps(sess: requests.Session, steps_date: str) -> dict:
    """Step data for a given date (YYYY-MM-DD)."""
    r = sess.get(
        f"{BASE}/wellness-service/wellness/dailySummaryChart/{steps_date}",
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_body_composition(sess: requests.Session, start_date: str, end_date: str) -> dict:
    """Body composition (weight, BMI, body fat…)."""
    r = sess.get(
        f"{BASE}/weight-service/weight/dateRange",
        params={"startDate": start_date, "endDate": end_date},
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


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    oauth2 = load_token()
    sess = make_session(oauth2)

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=7)).isoformat()

    print("─" * 10)
    print("PROFILE")
    print("─" * 10)
    profile = get_profile(sess)
    display_name = profile.get("displayName", "")
    print(f"  Name        : {profile.get('fullName', 'N/A')}")
    print(f"  Display name: {display_name}")
    print(f"  Location    : {profile.get('location', 'N/A')}")

    print("\n─" * 10)
    print("RECENT ACTIVITIES (last 5)")
    print("─" * 10)
    activities = get_activities(sess, limit=5)
    for act in activities:
        name = act.get("activityName", "?")
        sport = act.get("activityType", {}).get("typeKey", "?")
        dist = act.get("distance", 0) / 1000
        calories = act.get("calories") or 0
        dur = int(act.get("duration", 0))
        start_t = act.get("startTimeLocal", "?")
        print(f"  [{start_t}]  {sport:20s}  {dist:.2f} km  {dur//60}m{dur%60}s  {int(calories)} kcal  \"{name}\"")

    print("\n─" * 10)
    print(f"HEART RATE  ({yesterday})")
    print("─" * 10)
    try:
        hr = get_heart_rate(sess, yesterday)
        def fmt_hr(val): return f"{val} bpm" if val is not None else "N/A"
        print(f"  Resting HR : {fmt_hr(hr.get('restingHeartRate'))}")
        print(f"  Min HR     : {fmt_hr(hr.get('minHeartRate'))}")
        print(f"  Max HR     : {fmt_hr(hr.get('maxHeartRate'))}")
    except Exception as e:
        print(f"  (not available: {e})")

    print("\n─" * 10)
    print(f"SLEEP  ({yesterday})")
    print("─" * 10)
    try:
        sleep = get_daily_sleep(sess, yesterday)
        di = sleep.get("dailySleepDTO") or {}
        def fmt_sleep(key):
            v = di.get(key)
            return f"{v // 60} min" if v is not None else "N/A"
        total_s = di.get("sleepTimeSeconds")
        total_str = f"{total_s // 3600}h {(total_s % 3600) // 60}m" if total_s is not None else "N/A"
        print(f"  Total sleep : {total_str}")
        print(f"  Deep sleep  : {fmt_sleep('deepSleepSeconds')}")
        print(f"  Light sleep : {fmt_sleep('lightSleepSeconds')}")
        print(f"  REM sleep   : {fmt_sleep('remSleepSeconds')}")
        print(f"  Awake       : {fmt_sleep('awakeSleepSeconds')}")
    except Exception as e:
        print(f"  (not available: {e})")

    
    print("\n─" * 10)
    print(f"CALORIAS DO DIA  ({today})")
    print("─" * 10)
    try:
        summary = get_daily_summary(sess, display_name, today)
        total   = summary.get("totalKilocalories")
        active  = summary.get("activeKilocalories")
        bmr     = summary.get("bmrKilocalories")
        steps   = summary.get("totalSteps")
        dist_m  = summary.get("totalDistanceMeters")
        floors  = summary.get("floorsAscended")
        def fv(v, unit=""): return f"{v}{unit}" if v is not None else "N/A"
        print(f"  Total kcal  : {fv(total, ' kcal')}")
        print(f"  Ativas      : {fv(active, ' kcal')}")
        print(f"  BMR         : {fv(bmr, ' kcal')}")
        print(f"  Passos      : {fv(steps)}")
        print(f"  Distância   : {f'{dist_m/1000:.2f} km' if dist_m is not None else 'N/A'}")
        print(f"  Andares     : {fv(floors)}")
    except Exception as e:
        print(f"  (not available: {e})")

    print()


if __name__ == "__main__":
    main()
