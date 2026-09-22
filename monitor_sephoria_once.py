#!/usr/bin/env python3
"""
SEPHORiA London resale ticket monitor — single-run version for GitHub Actions.

Each run: fetches the resale page(s), compares to the last saved state
(monitor_state.json, committed back to the repo by the workflow), and
pushes a phone notification via ntfy.sh if something changed.

NTFY_TOPIC is read from an environment variable (set as a GitHub Actions
secret) rather than hardcoded here.
"""

import requests
from bs4 import BeautifulSoup
import hashlib
import json
import os
import sys
from datetime import datetime

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

URLS_TO_CHECK = [
    "https://widget.weezevent.com/ticket/resale-sephoria-london-2026?locale=en-gb",
    "https://sites.weezevent.com/sephoria-london/",
]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_state.json")

SOLD_OUT_SIGNALS = ["sold out", "no tickets available", "unavailable", "épuisé", "complet"]
AVAILABLE_SIGNALS = ["add to basket", "add to cart", "buy now", "book now", "purchase",
                      "select", "quantity", "£95", "£75"]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def extract_signal(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    text_lower = text.lower()

    has_sold_out = any(sig in text_lower for sig in SOLD_OUT_SIGNALS)
    has_available = any(sig in text_lower for sig in AVAILABLE_SIGNALS)
    looks_available = has_available and not has_sold_out

    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text_hash, looks_available


def notify(title, message, url, priority="default"):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set — skipping notification.")
        return
    try:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": "ticket", "Click": url},
            timeout=15,
        )
        print(f"[{datetime.now()}] Notification sent: {title}")
    except Exception as e:
        print(f"[{datetime.now()}] Failed to send notification: {e}")


def check_url(url, state):
    try:
        html = fetch(url)
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching {url}: {e}")
        return

    text_hash, looks_available = extract_signal(html)
    prev = state.get(url, {})
    was_available = prev.get("looks_available", False)

    status = "AVAILABLE ✅" if looks_available else "Sold out ❌"
    print(f"[{datetime.now()}] {url} -> {status}")

    # Only notify on the transition into "available" — silent otherwise.
    if looks_available and not was_available:
        notify(
            "🎟️ SEPHORiA London — tickets may be available!",
            f"Availability signal detected. Check now:\n{url}",
            url,
            priority="urgent",
        )

    state[url] = {"hash": text_hash, "looks_available": looks_available}


def main():
    state = load_state()
    for url in URLS_TO_CHECK:
        check_url(url, state)
    save_state(state)


if __name__ == "__main__":
    main()
