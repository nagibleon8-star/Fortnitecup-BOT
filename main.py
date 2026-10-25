import os
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
print("webhook",webhook_url)
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
CALENDAR_FILE = "events.ics"
SENT_FILE = "sent.json"

VIENNA = ZoneInfo("Europe/Vienna")


def load_events():
    with open(CALENDAR_FILE, "r", encoding="utf-8-sig") as file:
        content = file.read()

    # Zusammengehörige iCal-Zeilen verbinden
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

        date_key, date_value = get_value("DTSTART")
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

    message = {
        "username": "Fortnite Tournaments",
        "embeds": [{
            "title": "🏆 " + event["name"],
            "description": (
                "Ein Fortnite-Turnier startet "
                "innerhalb der nächsten 24 Stunden!"
            ),
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
                "text": "Grinder Grinders | Fortnite Cups"
            }
        }]
    }

    if event["link"].startswith("https://"):
        message["embeds"][0]["url"] = event["link"]

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(message).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=20):
        pass


def main():
    if not WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL fehlt.")
        return

    if not os.path.exists(CALENDAR_FILE):
        print("events.ics fehlt.")
        return

    sent = []

    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r", encoding="utf-8") as file:
            sent = json.load(file)

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)

    for event in load_events():
        start = event["start"].astimezone(timezone.utc)

        if now <= start <= deadline:
            if event["id"] not in sent:
                send_discord(event)
                sent.append(event["id"])
                print("Angekündigt:", event["name"])

    with open(SENT_FILE, "w", encoding="utf-8") as file:
        json.dump(sent, file, indent=2)


if __name__ == "__main__":
    main()
