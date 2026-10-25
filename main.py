import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
CALENDAR_URL = "https://fortnitetracker.com/events.ics?region=EU"
SENT_FILE = "sent.json"

VIENNA = ZoneInfo("Europe/Vienna")


def load_events():
    request = urllib.request.Request(
        CALENDAR_URL,
        headers={"User-Agent": "Mozilla/5.0 FortniteCupBot/1.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read().decode("utf-8-sig")

    content = content.replace("\r\n", "\n")
    content = content.replace("\n ", "").replace("\n\t", "")

    events = []

    for block in content.split("BEGIN:VEVENT")[1:]:
        block = block.split("END:VEVENT")[0]
        data = {}

        for line in block.splitlines():
            if ":" not in line:
                continue

            key, value = line.split(":", 1)
            data[key] = value

        def get_value(name):
            for key, value in data.items():
                if key.split(";")[0] == name:
                    return key, value
            return None, None

        _, date_value = get_value("DTSTART")
        _, name = get_value("SUMMARY")
        _, link = get_value("URL")
        _, uid = get_value("UID")

        if not date_value or not name:
            continue

        try:
            if date_value.endswith("Z"):
                start = datetime.strptime(
                    date_value, "%Y%m%dT%H%M%SZ"
                ).replace(tzinfo=timezone.utc)
            elif "T" in date_value:
                start = datetime.strptime(
                    date_value, "%Y%m%dT%H%M%S"
                ).replace(tzinfo=VIENNA)
            else:
                start = datetime.strptime(
                    date_value, "%Y%m%d"
                ).replace(tzinfo=VIENNA)

            events.append({
                "id": uid or name + date_value,
                "name": name.replace("\\,", ","),
                "start": start,
                "link": link or ""
            })

        except ValueError:
            continue

    return events


def send_discord(event):
    start = event["start"].astimezone(VIENNA)

    embed = {
        "title": "🏆 " + event["name"],
        "description": "Ein Fortnite-Turnier startet innerhalb der nächsten 24 Stunden!",
        "color": 3447003,
        "fields": [
            {
                "name": "📅 Datum",
                "value": start.strftime("%d.%m.%Y"),
                "inline": True
            },
            {
                "name": "⏰ Uhrzeit",
                "value": start.strftime("%H:%M") + " Uhr",
                "inline": True
            },
            {
                "name": "🌍 Region",
                "value": "Europa",
                "inline": True
            }
        ],
        "footer": {
            "text": "Grinder | Fortnite Cups"
        }
    }

    if event["link"].startswith("https://"):
        embed["url"] = event["link"]

    message = {
        "username": "Fortnite Tournaments",
        "embeds": [embed]
    }

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(message).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FortniteCupBot/1.0"
        },
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20):
        pass


def main():
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL fehlt in GitHub Secrets.")

    events = load_events()

    sent = []
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, "r", encoding="utf-8") as file:
                sent = json.load(file)
        except (json.JSONDecodeError, OSError):
            sent = []

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)
    sent_ids = set(sent)

    for event in events:
        start = event["start"].astimezone(timezone.utc)

        if now <= start <= deadline and event["id"] not in sent_ids:
            send_discord(event)
            sent_ids.add(event["id"])
            print("Angekündigt:", event["name"])

    with open(SENT_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(sent_ids), file, indent=2)


if __name__ == "__main__":
    main()
