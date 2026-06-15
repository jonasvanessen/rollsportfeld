#!/usr/bin/env python3
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.sportanlagen-app.net/Public/Spielplan"
QUERY = "k=6&m=Gr%C3%BCnStadtZ%C3%BCrich&size=9"
TARGET_FIELD = "Rollsportfeld"

WEEKDAYS_DE = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag"
]


def fetch_page(tag: int) -> str:
    url = f"{BASE_URL}?{QUERY}&tag={tag}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.text


def extract_date(html: str) -> str | None:
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})", html)
    return m.group(1) if m else None


def parse_bookings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    bookings = []

    for tr in soup.find_all("tr", role="row"):
        tds = tr.find_all("td", role="gridcell")
        if not tds:
            continue

        cells = {}
        for td in tds:
            idx = td.get("data-col-index")
            if idx is not None:
                cells[int(idx)] = td.get_text(separator=" ", strip=True)

        if cells.get(4, "") != TARGET_FIELD:
            continue

        bookings.append({
            "time": cells.get(0, ""),
            "team": cells.get(2, ""),
            "gast": cells.get(3, ""),
            "flaeche": cells.get(5, ""),
            "typ": cells.get(6, ""),
        })

    return bookings


def weekday_name(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%d.%m.%Y")
        return WEEKDAYS_DE[d.weekday()]
    except ValueError:
        return ""


def generate_html(days: list[dict], generated_at: str) -> str:
    cards = []
    for day in days:
        date_str = day["date"] or f"Tag {day['tag']}"
        bookings = day["bookings"]
        wday = weekday_name(date_str) if day["date"] else ""
        label = f"{wday}, {date_str}" if wday else date_str

        if not bookings:
            status_html = '<p class="badge free">&#10003; Frei</p>'
        else:
            rows = "".join(
                f"<tr><td>{b['time']}</td><td>{b['team'] or '—'}</td><td>{b['typ']}</td></tr>"
                for b in bookings
            )
            status_html = (
                '<p class="badge busy">Belegt</p>'
                '<table class="bookings">'
                "<thead><tr><th>Zeit</th><th>Team</th><th>Typ</th></tr></thead>"
                f"<tbody>{rows}</tbody>"
                "</table>"
            )

        card_class = "card free" if not bookings else "card busy"
        cards.append(f'<div class="{card_class}"><h2>{label}</h2>{status_html}</div>')

    cards_html = "\n".join(cards)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Rollsportfeld – Belegungsplan</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #f0f2f5;
      color: #1a1a2e;
      padding: 1.5rem;
    }}
    header {{
      text-align: center;
      margin-bottom: 2rem;
    }}
    header h1 {{
      font-size: 1.8rem;
      font-weight: 700;
      color: #1a1a2e;
    }}
    header p {{
      color: #666;
      font-size: 0.85rem;
      margin-top: 0.3rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 1rem;
      max-width: 1100px;
      margin: 0 auto;
    }}
    .card {{
      background: #fff;
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
      border-top: 4px solid transparent;
    }}
    .card.free  {{ border-top-color: #22c55e; }}
    .card.busy  {{ border-top-color: #f97316; }}
    .card h2 {{
      font-size: 1rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
    }}
    .badge {{
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
      margin-bottom: 0.5rem;
    }}
    .badge.free {{ background: #dcfce7; color: #15803d; }}
    .badge.busy {{ background: #ffedd5; color: #c2410c; }}
    .bookings {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      margin-top: 0.5rem;
    }}
    .bookings th, .bookings td {{
      text-align: left;
      padding: 0.35rem 0.5rem;
      border-bottom: 1px solid #f0f0f0;
    }}
    .bookings thead th {{
      color: #888;
      font-weight: 500;
      font-size: 0.75rem;
      text-transform: uppercase;
    }}
    @media (max-width: 480px) {{
      body {{ padding: 1rem; }}
      header h1 {{ font-size: 1.3rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Rollsportfeld &ndash; Belegungsplan</h1>
    <p>Automatisch aktualisiert: {generated_at} UTC</p>
  </header>
  <div class="grid">
    {cards_html}
  </div>
</body>
</html>
"""


def main():
    days = []
    for tag in range(11):
        print(f"Fetching tag={tag}…", file=sys.stderr)
        try:
            html = fetch_page(tag)
            date_str = extract_date(html)
            bookings = parse_bookings(html)
            days.append({"tag": tag, "date": date_str, "bookings": bookings})
        except Exception as exc:
            print(f"  Error on tag={tag}: {exc}", file=sys.stderr)
            days.append({"tag": tag, "date": None, "bookings": []})

    # Fill in missing dates using tag=0's date as the anchor
    anchor: datetime | None = None
    for d in days:
        if d["date"] and d["tag"] == 0:
            try:
                anchor = datetime.strptime(d["date"], "%d.%m.%Y")
            except ValueError:
                pass
            break
    if anchor is None:
        anchor = datetime.now(timezone.utc).replace(tzinfo=None)

    for d in days:
        if d["date"] is None:
            d["date"] = (anchor + timedelta(days=d["tag"])).strftime("%d.%m.%Y")

    # Sort chronologically
    def sort_key(d):
        try:
            return datetime.strptime(d["date"], "%d.%m.%Y")
        except (ValueError, TypeError):
            return datetime.min + timedelta(days=d["tag"])

    days.sort(key=sort_key)

    generated_at = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    html_out = generate_html(days, generated_at)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_out)

    print("index.html written.", file=sys.stderr)

    # Summary
    booked_days = sum(1 for d in days if d["bookings"])
    print(
        f"Days with Rollsportfeld bookings: {booked_days}/{len(days)}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
