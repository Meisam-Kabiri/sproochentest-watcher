import json
import os
import smtplib
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

URL = "https://myinl.inll.lu/exam/offer/sproochentest-8"
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "state", "status.json")
EMAIL_ADDRESS = "msm.kabiri91@gmail.com"

CLOSED_STATUSES = {"sold out", "registration closed", "suspens"}


def fetch_sessions():
    resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
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
                "status": cells[6].get_text(strip=True),
            }
        )
    return sessions


def is_available(status):
    return status.strip().lower() not in CLOSED_STATUSES


def session_key(session):
    return f"{session['session']}|{session['written_exam']}|{session['location']}"


def load_previous_sessions():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            data = json.load(f)
        return {session_key(s): s for s in data.get("sessions", [])}
    return {}


def save_state(sessions):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"sessions": sessions}, f, indent=2)


def send_email(newly_available):
    password = os.environ["GMAIL_APP_PASSWORD"]
    lines = ["A Sproochentest session status changed to available:\n"]
    for s in newly_available:
        lines.append(
            f"- {s['session']} | {s['mode']} | {s['location']} | "
            f"written: {s['written_exam']} | status: {s['status']}"
        )
    lines.append(f"\nCheck and register here: {URL}")
    msg = MIMEText("\n".join(lines))
    msg["Subject"] = "Sproochentest slot may be available!"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, password)
        server.sendmail(EMAIL_ADDRESS, [EMAIL_ADDRESS], msg.as_string())


def main():
    sessions = fetch_sessions()
    if not sessions:
        print("No session rows found — page structure may have changed.")
        return

    previous = load_previous_sessions()
    newly_available = []
    for s in sessions:
        was_available = is_available(previous.get(session_key(s), {}).get("status", "Sold Out"))
        now_available = is_available(s["status"])
        if now_available and not was_available:
            newly_available.append(s)

    if newly_available:
        print(f"Newly available: {newly_available}")
        send_email(newly_available)
    else:
        print("No new availability.")

    save_state(sessions)


if __name__ == "__main__":
    main()
