import json
import os
import smtplib
import time
import uuid
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

URL = "https://myinl.inll.lu/exam/offer/sproochentest-8"
STATE_FILE = os.environ.get(
    "STATE_FILE", os.path.join(os.path.dirname(__file__), "..", "state", "status.json")
)
EMAIL_ADDRESS = "msm.kabiri91@gmail.com"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "sproochentest-mk-7f3a9c2e41")

CLOSED_STATUSES = {"sold out", "registration closed", "suspens"}
# Fewer real (non-"Suspens") sessions than this means we were probably served a broken/stale page.
MIN_EXPECTED_SESSIONS = 2
REALERT_SECONDS = 30 * 60
HEALTH_ALERT_SECONDS = 24 * 60 * 60


def fetch_sessions():
    resp = requests.get(
        URL,
        params={"_": uuid.uuid4().hex},
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    sessions = []
    for row in soup.select("table.OfferExamTable tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        sessions.append(
            {
                "session": cells[0].get_text(strip=True),
                "mode": cells[1].get_text(strip=True),
                "location": cells[2].get_text(strip=True),
                "written_exam": cells[3].get_text(strip=True),
                "oral_exam": cells[4].get_text(strip=True),
                "registration_deadline": cells[5].get_text(strip=True),
                "status": cells[6].get_text(" ", strip=True),
            }
        )
    return sessions


def is_available(status):
    return status.strip().lower() not in CLOSED_STATUSES


def session_key(session):
    return f"{session['session']}|{session['written_exam']}|{session['location']}"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_email(subject, body):
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not password:
        print("GMAIL_APP_PASSWORD not set — skipping email.")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, password)
        server.sendmail(EMAIL_ADDRESS, [EMAIL_ADDRESS], msg.as_string())


def send_push(title, body, priority="urgent"):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode(),
            headers={"Title": title, "Priority": priority, "Click": URL, "Tags": "rotating_light"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"Push failed: {e}")


def notify(subject, body, priority="urgent"):
    # Each channel is independent: one failing must not suppress the other.
    send_push(subject, body, priority)
    try:
        send_email(subject, body)
    except Exception as e:
        print(f"Email failed: {e}")


def main():
    state = load_state()
    previous = {session_key(s): s for s in state.get("sessions", [])}
    last_alerts = state.get("last_alerts", {})
    now = time.time()

    try:
        sessions = fetch_sessions()
    except requests.RequestException as e:
        sessions = []
        print(f"Fetch failed: {e}")

    for s in sessions:
        print(f"  {s['session']:<28} {s['status']}")

    real_sessions = [s for s in sessions if s["session"].lower() != "suspens"]
    if len(real_sessions) < MIN_EXPECTED_SESSIONS:
        print(f"Only {len(real_sessions)} session rows parsed — page looks broken or stale.")
        if now - state.get("last_health_alert", 0) > HEALTH_ALERT_SECONDS:
            notify(
                "Sproochentest watcher may be BROKEN",
                f"The watcher only found {len(real_sessions)} sessions on {URL}.\n"
                "It may be getting a stale/blocked page. Check the site manually.",
                priority="high",
            )
            state["last_health_alert"] = now
        save_state(state)
        return

    to_alert = []
    for s in sessions:
        key = session_key(s)
        if not is_available(s["status"]):
            last_alerts.pop(key, None)
            continue
        was_available = is_available(previous.get(key, {}).get("status", "Sold Out"))
        # Alert on transition, and keep re-alerting while it stays open so it can't be missed.
        if not was_available or now - last_alerts.get(key, 0) > REALERT_SECONDS:
            to_alert.append(s)
            last_alerts[key] = now

    if to_alert:
        print(f"Available: {to_alert}")
        lines = ["Sproochentest seats look AVAILABLE:\n"]
        for s in to_alert:
            lines.append(
                f"- {s['session']} | {s['mode']} | {s['location']} | "
                f"written: {s['written_exam']} | status: {s['status']}"
            )
        lines.append(f"\nRegister NOW: {URL}")
        notify("Sproochentest SEAT AVAILABLE - register now!", "\n".join(lines))
    else:
        print("No availability.")

    state["sessions"] = sessions
    state["last_alerts"] = last_alerts
    save_state(state)


if __name__ == "__main__":
    main()
