"""
GenerateTokenGarmin.py — Get Garmin OAuth2 tokens via browser login (Playwright).

Based on:
  coleman8er/garmin-browser-auth.py
  https://github.com/coleman8er/garmin-browser-auth

Bypasses the 429-blocked SSO programmatic login endpoint using browser automation.

Usage:
  python GenerateTokenGarmin.py

First time setup (installs Chromium):
  playwright install chromium
"""
import base64
import getpass
import json
import re
import time
from pathlib import Path
from typing import List
from typing import Optional
from typing import Tuple
from urllib.parse import parse_qs

import requests
from requests_oauthlib import OAuth1Session
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright


OAUTH_CONSUMER_URL = "https://thegarth.s3.amazonaws.com/oauth_consumer.json"
ANDROID_UA = "com.garmin.android.apps.connectmobile"
DEFAULT_SSO_URL = (
    "https://sso.garmin.com/sso/embed"
    "?id=gauth-widget"
    "&embedWidget=true"
    "&gauthHost=https://sso.garmin.com/sso"
    "&clientId=GarminConnect"
    "&locale=en_US"
    "&redirectAfterAccountLoginUrl=https://sso.garmin.com/sso/embed"
    "&service=https://sso.garmin.com/sso/embed"
)


def get_oauth_consumer():
    """Fetch the shared OAuth consumer key/secret from garth's S3 bucket."""
    resp = requests.get(OAUTH_CONSUMER_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_oauth1_token(ticket: str, consumer: dict) -> dict:
    """Exchange an SSO ticket for an OAuth1 token."""
    sess = OAuth1Session(
        consumer["consumer_key"],
        consumer["consumer_secret"],
    )
    url = (
        f"https://connectapi.garmin.com/oauth-service/oauth/"
        f"preauthorized?ticket={ticket}"
        f"&login-url=https://sso.garmin.com/sso/embed"
        f"&accepts-mfa-tokens=true"
    )
    resp = sess.get(url, headers={"User-Agent": ANDROID_UA}, timeout=15)
    resp.raise_for_status()
    parsed = parse_qs(resp.text)
    token = {k: v[0] for k, v in parsed.items()}
    token["domain"] = "garmin.com"
    return token


def exchange_oauth2(oauth1: dict, consumer: dict) -> dict:
    """Exchange OAuth1 token for OAuth2 token."""
    sess = OAuth1Session(
        consumer["consumer_key"],
        consumer["consumer_secret"],
        resource_owner_key=oauth1["oauth_token"],
        resource_owner_secret=oauth1["oauth_token_secret"],
    )
    url = "https://connectapi.garmin.com/oauth-service/oauth/exchange/user/2.0"
    data = {}
    if oauth1.get("mfa_token"):
        data["mfa_token"] = oauth1["mfa_token"]
    resp = sess.post(
        url,
        headers={
            "User-Agent": ANDROID_UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json()
    token["expires_at"] = int(time.time() + token["expires_in"])
    token["refresh_token_expires_at"] = int(
        time.time() + token["refresh_token_expires_in"]
    )
    return token


def _fill_first(page: Page, selectors: List[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count():
                locator.wait_for(state="visible", timeout=5000)
                locator.fill(value)
                return True
        except Exception:
            continue
    return False


def _click_first(page: Page, selectors: List[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count():
                locator.wait_for(state="visible", timeout=5000)
                locator.click()
                return True
        except Exception:
            continue
    return False


def autofill_login(page: Page, username: str, password: str) -> bool:
    """Best-effort Garmin SSO autofill; falls back to manual continuation."""
    page.wait_for_timeout(1500)

    username_ok = _fill_first(
        page,
        [
            "input[name='username']",
            "input[type='email']",
            "input[autocomplete='username']",
            "input[id='email']",
        ],
        username,
    )
    password_ok = _fill_first(
        page,
        [
            "input[name='password']",
            "input[type='password']",
            "input[autocomplete='current-password']",
        ],
        password,
    )

    if not (username_ok and password_ok):
        return False

    _click_first(
        page,
        [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Sign In')",
            "button:has-text('Entrar')",
            "button:has-text('Log In')",
        ],
    )
    return True


def browser_login(username: Optional[str] = None, password: Optional[str] = None) -> str:
    """Open a real browser, optionally autofill credentials, and capture the SSO ticket."""
    ticket = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto(DEFAULT_SSO_URL, wait_until="domcontentloaded")

        print()
        print("=" * 50)
        if username and password:
            print("  Browser opened — trying to fill your Garmin")
            print("  credentials automatically. If Garmin asks")
            print("  for MFA or extra confirmation, finish it")
            print("  in the opened window.")
        else:
            print("  Browser opened — log in with your Garmin")
            print("  credentials. The window will close")
            print("  automatically when done.")
        print("=" * 50)
        print()

        if username and password:
            filled = autofill_login(page, username, password)
            if filled:
                print("Login form filled automatically. Waiting for Garmin to finish authentication...")
            else:
                print("Could not autofill the login form. Continue manually in the browser window.")

        # Wait for the success redirect that contains the ticket
        # The SSO flow ends with a page containing 'ticket=ST-...'
        max_wait = 300  # 5 minutes
        start = time.time()
        while time.time() - start < max_wait:
            try:
                content = page.content()
                # Look for ticket in page content (ST- prefix)
                m = re.search(r'ticket=(ST-[A-Za-z0-9\-]+)', content)
                if m:
                    ticket = m.group(1)
                    print(f"Got ticket: {ticket[:30]}...")
                    break

                # Also check URL for ticket param
                url = page.url
                if "ticket=" in url:
                    m = re.search(r'ticket=(ST-[A-Za-z0-9\-]+)', url)
                    if m:
                        ticket = m.group(1)
                        print(f"Got ticket from URL: {ticket[:30]}...")
                        break
            except Exception:
                pass

            page.wait_for_timeout(500)

        browser.close()

    if not ticket:
        print("ERROR: Timed out waiting for login (5 min). Try again.")
        raise SystemExit(1)

    return ticket


def verify_oauth2_token(oauth2: dict) -> dict:
    """Verify the OAuth2 token and return the authenticated profile."""
    verify_resp = requests.get(
        "https://connectapi.garmin.com/userprofile-service/socialProfile",
        headers={
            "User-Agent": "GCM-iOS-5.7.2.1",
            "Authorization": f"Bearer {oauth2['access_token']}",
        },
        timeout=15,
    )
    verify_resp.raise_for_status()
    return verify_resp.json()


def save_tokens(oauth1: dict, oauth2: dict) -> Path:
    """Save OAuth tokens in the local garth folder."""
    garth_dir = Path.home() / ".garth"
    garth_dir.mkdir(exist_ok=True)
    (garth_dir / "oauth1_token.json").write_text(json.dumps(oauth1, indent=2))
    (garth_dir / "oauth2_token.json").write_text(json.dumps(oauth2, indent=2))
    return garth_dir


def build_token_bundle(oauth1: dict, oauth2: dict) -> Tuple[dict, str]:
    """Return the token bundle as dict and base64 string."""
    bundle = {"oauth1": oauth1, "oauth2": oauth2}
    b64 = base64.b64encode(json.dumps(bundle).encode()).decode()
    return bundle, b64


def generate_token_bundle(
    username: Optional[str] = None,
    password: Optional[str] = None,
    save_local_copy: bool = False,
    verify: bool = True,
) -> Tuple[dict, Optional[dict]]:
    """Generate Garmin OAuth1/OAuth2 tokens and optionally verify them."""
    consumer = get_oauth_consumer()
    ticket = browser_login(username=username, password=password)
    oauth1 = get_oauth1_token(ticket, consumer)
    oauth2 = exchange_oauth2(oauth1, consumer)

    profile = verify_oauth2_token(oauth2) if verify else None
    if save_local_copy:
        save_tokens(oauth1, oauth2)

    bundle, _ = build_token_bundle(oauth1, oauth2)
    return bundle, profile


def prompt_credentials() -> Tuple[str, str]:
    """Prompt the user for Garmin credentials."""
    username = input("Email Garmin: ").strip()
    if not username:
        raise RuntimeError("Email Garmin is required")
    password = getpass.getpass("Senha Garmin: ").strip()
    if not password:
        raise RuntimeError("Senha Garmin is required")
    return username, password


def main():
    print("Garmin Browser Auth")
    print("=" * 50)

    username, password = prompt_credentials()

    print("Fetching OAuth consumer credentials...")
    consumer = get_oauth_consumer()

    print("Launching browser...")
    ticket = browser_login(username=username, password=password)

    print("Exchanging ticket for OAuth1 token...")
    oauth1 = get_oauth1_token(ticket, consumer)
    print(f"  OAuth1 token: {oauth1['oauth_token'][:20]}...")

    print("Exchanging OAuth1 for OAuth2 token...")
    oauth2 = exchange_oauth2(oauth1, consumer)
    print(f"  OAuth2 access_token: {oauth2['access_token'][:20]}...")
    print(f"  Expires in: {oauth2['expires_in']}s")
    print(f"  Refresh expires in: {oauth2['refresh_token_expires_in']}s")

    print("Verifying tokens...")
    profile = verify_oauth2_token(oauth2)
    print(f"  Authenticated as: {profile.get('displayName', 'unknown')}")

    garth_dir = save_tokens(oauth1, oauth2)
    print(f"\nTokens saved to {garth_dir}")

    _, b64 = build_token_bundle(oauth1, oauth2)

    print("\n" + "=" * 50)
    print("GARMIN_TOKEN_B64 (paste into GitHub secret):")
    print("=" * 50)
    print(b64)
    print("=" * 50)


if __name__ == "__main__":
    main()
