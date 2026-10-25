import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
CITO_API_KEY = os.environ.get("CITO_API_KEY", "")

API_URL = "https://api.citoapi.com/api/v1/fortnite/tournaments/upcoming"

SENT_FILE = "sent.json"
VIENNA = ZoneInfo("Europe/Vienna")


def fetch_tournaments():
    params = urlencode({
        "region": "EU",
        "status": "5",
        "limit": 100
    })

    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={
            "x-api-key": CITO_API_KEY,
            "Accept": "application/json",
            "User-Agent": "FortniteCupBot/1.0"
        }
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Cito API HTTP {error.code}: {details}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Cito API nicht erreichbar: {error}"
        ) from error

    if not result.get("success", False):
        raise RuntimeError(
            f"Cito API Fehler: {result}"
        )

    data = result.get("data", [])

    if isinstance(data, dict):
        data = data.get("tournaments", data.get("events", []))

    if not isinstance(data, list):
        raise RuntimeError(
            "Unerwartetes Datenformat der Cito API."
        )

    print(f"Cito API: {len(data)} Turniere erhalten.")
    print("Beispiel-Turnier:", json.dumps(data[0], indent=2) if data else "Keine Daten")
    return data


def parse_date(value):
    if not value:
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(
                value, timezone.utc
            )
        except (ValueError, OSError, OverflowError):
            return None

    if not isinstance(value, str):
        return None

    value = value.strip()

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=VIENNA)

        return parsed

    except ValueError:
        pass

    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            parsed = datetime.strptime(value, fmt)

            if fmt.endswith("Z"):
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.replace(tzinfo=VIENNA)

            return parsed

        except ValueError:
            continue

    return None


def get_start(tournament):
    for key in (
        "startTime",
        "start_time",
        "startDate",
        "start_date",
        "startAt",
        "startsAt",
        "start",
        "scheduledStart",
        "date"
    ):
        if tournament.get(key):
            parsed = parse_date(tournament[key])

            if parsed:
                return parsed

    return None


def get_name(tournament):
    for key in ("name", "title", "displayName", "eventName"):
        value = tournament.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return "Fortnite-Turnier"


def get_link(tournament):
    identifiers = tournament.get("identifiers", {})

    if not isinstance(identifiers, dict):
        identifiers = {}

    for value in (
        tournament.get("url"),
        tournament.get("source_url"),
        tournament.get("sourceUrl"),
        identifiers.get("source_url"),
        identifiers.get("sourceUrl")
    ):
        if isinstance(value, str) and value.startswith("https://"):
            return value

    return ""


def get_event_id(tournament):
    for key in ("id", "tournamentId", "eventId", "slug"):
        value = tournament.get(key)

        if value:
            return str(value)

    return get_name(tournament)


def load_sent():
    if not os.path.exists(SENT_FILE):
        return set()

    try:
        with open(SENT_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return set(str(item) for item in data)

    except (json.JSONDecodeError, OSError):
        print("Warnung: sent.json konnte nicht gelesen werden.")

    return set()


def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(sent), file, indent=2)


def send_discord(tournament, start):
    name = get_name(tournament)
    link = get_link(tournament)

    embed = {
        "title": f"🏆 {name}",
        "description": (
            "Ein Fortnite-Turnier startet innerhalb "
            "der nächsten 24 Stunden!"
        ),
        "color": 3447003,
        "fields": [
            {
                "name": "📅 Datum",
                "value": start.astimezone(VIENNA).strftime("%d.%m.%Y"),
                "inline": True
            },
            {
                "name": "⏰ Uhrzeit",
                "value": (
                    start.astimezone(VIENNA).strftime("%H:%M")
                    + " Uhr"
                ),
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

    if link:
        embed["url"] = link

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
    if not CITO_API_KEY:
        raise RuntimeError(
            "CITO_API_KEY fehlt. Prüfe das GitHub Secret "
            "und die Umgebungsvariablen im Workflow."
        )

    if not WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL fehlt in GitHub Secrets."
        )

    tournaments = fetch_tournaments()

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)

    sent = load_sent()
    changed = False
    found = 0

    for tournament in tournaments:
        if not isinstance(tournament, dict):
            continue

        name = get_name(tournament)
        start = get_start(tournament)

        if start is None:
            print(
                "Übersprungen: Kein erkennbares Startdatum für",
                name
            )
            continue

        start_utc = start.astimezone(timezone.utc)

        if not now <= start_utc <= deadline:
            continue

        event_id = get_event_id(tournament)

        if event_id in sent:
            continue

        send_discord(tournament, start)

        sent.add(event_id)
        changed = True
        found += 1

        print("Angekündigt:", name)

    if changed:
        save_sent(sent)

    if found == 0:
        print(
            "Keine neuen Turniere innerhalb der nächsten "
            "24 Stunden gefunden."
        )


if __name__ == "__main__":
    main()
