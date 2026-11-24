#!/usr/bin/env python3
"""Fetch FD rates from hnbfinance.lk and update rates.json.

- Always refreshes `lastChecked`.
- Updates `lastChanged` (and effective date) only when the rates really changed.
- Refuses to overwrite rates.json if the page layout looks broken.
"""
import json, re, sys, datetime, pathlib
import requests
from bs4 import BeautifulSoup

URL = "https://www.hnbfinance.lk/fixed-deposits/"
OUT = pathlib.Path(__file__).resolve().parent.parent / "rates.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (FD-rate-sync; +https://github.com)"}


def pct(text):
    t = text.strip().replace("%", "").replace(",", "")
    if t in ("", "–", "-", "—"):
        return None
    return float(t)


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    rates = {}
    for table in soup.find_all("table"):
        heading = table.find_previous(["h1", "h2", "h3", "h4"])
        htxt = heading.get_text(" ", strip=True).lower() if heading else ""
        if "interest rate" not in htxt:
            continue
        kind = "senior" if "senior" in htxt else "general"
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 5:
                continue
            m = re.match(r"(\d+)\s*month", cells[0], re.I)
            if not m:
                continue
            months = m.group(1)
            entry = {
                "monthly": pct(cells[1]), "monthlyNet": pct(cells[2]),
                "maturity": pct(cells[3]), "maturityNet": pct(cells[4]),
            }
            rates.setdefault(months, {"general": None, "senior": None})[kind] = entry
    # effective date from the Key Fact Document link, e.g. ..._01_10.2026.pdf
    eff = None
    for a in soup.find_all("a", href=True):
        if "key_fact_document_fixed" in a["href"].lower():
            m = re.search(r"(\d{2})[_.](\d{2})[_.](\d{4})", a["href"])
            if m:
                d = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                suf = "th" if 11 <= d.day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
                eff = f"{d.day:02d}{suf} {d.strftime('%B %Y')}"
    return rates, eff


def main():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    rates, eff = parse(r.text)

    general = [k for k, v in rates.items() if v["general"]]
    if len(general) < 10:
        sys.exit(f"Parse looks wrong ({len(general)} general rows). rates.json NOT changed.")

    rates = dict(sorted(rates.items(), key=lambda kv: int(kv[0])))
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    changed = old.get("rates") != rates

    new = {
        "source": URL,
        "lastChecked": now,
        "lastChanged": now if changed else old.get("lastChanged", now),
        "effectiveDate": eff or old.get("effectiveDate"),
        "ref": old.get("ref") if (eff or old.get("effectiveDate")) == old.get("effectiveDate") else None,
        "rates": rates,
    }
    OUT.write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n")
    print("RATES CHANGED" if changed else "No change", "-", now)


if __name__ == "__main__":
    main()
