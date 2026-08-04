# -*- coding: utf-8 -*-
"""
fetch_odds.py  --  laeuft in GitHub Actions (Cloud, freier Netzzugang).

Holt Bundesliga-Quoten von The Odds API, bildet je Spiel den BUCHMACHER-KONSENS
(Median je Wettausgang) und schreibt eine kompakte `odds_bl1.json`. Diese Datei
wird von der Action zurueck ins Repo committet und vom lokalen Bundesliga-Tipp-
Tool ueber raw.githubusercontent.com gelesen (der einzige Weg an Quoten-Daten,
da der Firmen-Proxy alle Quoten-Anbieter direkt sperrt).

* Nur Python-Standardbibliothek (laeuft mit dem Python der GitHub-Runner).
* API-Key kommt aus der Umgebungsvariable ODDS_API_KEY (GitHub Secret).
* Kosten pro Lauf: markets(2) x regions(1) = 2 Credits. Free-Plan = 500/Monat.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from statistics import median

SPORT = "soccer_germany_bundesliga"
REGIONS = "eu"                 # europaeische Buchmacher
MARKETS = "h2h,totals"         # 1X2 + Ueber/Unter
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odds_bl1.json")


def main():
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        print("FEHLER: Umgebungsvariable ODDS_API_KEY ist leer/nicht gesetzt.",
              file=sys.stderr)
        return 2

    url = ("https://api.the-odds-api.com/v4/sports/%s/odds/"
           "?apiKey=%s&regions=%s&markets=%s&oddsFormat=decimal&dateFormat=iso"
           % (SPORT, key, REGIONS, MARKETS))
    req = urllib.request.Request(url, headers={"User-Agent": "bl-odds-tunnel/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            events = json.loads(resp.read().decode("utf-8"))
            remaining = resp.headers.get("x-requests-remaining")
            used = resp.headers.get("x-requests-used")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print("HTTP %s von The Odds API: %s" % (e.code, body), file=sys.stderr)
        return 3
    except Exception as e:
        print("Abruf fehlgeschlagen: %r" % e, file=sys.stderr)
        return 3

    matches = []
    for ev in events:
        home = ev.get("home_team")
        away = ev.get("away_team")
        if not home or not away:
            continue
        h2h_home, h2h_draw, h2h_away = [], [], []
        totals = {}  # point -> {"over": [...], "under": [...]}
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                mkey = mk.get("key")
                if mkey == "h2h":
                    for oc in mk.get("outcomes", []):
                        nm, pr = oc.get("name"), oc.get("price")
                        if pr is None:
                            continue
                        if nm == home:
                            h2h_home.append(pr)
                        elif nm == away:
                            h2h_away.append(pr)
                        elif nm == "Draw":
                            h2h_draw.append(pr)
                elif mkey == "totals":
                    for oc in mk.get("outcomes", []):
                        pt, nm, pr = oc.get("point"), oc.get("name"), oc.get("price")
                        if pt is None or pr is None:
                            continue
                        slot = totals.setdefault(float(pt), {"over": [], "under": []})
                        if nm == "Over":
                            slot["over"].append(pr)
                        elif nm == "Under":
                            slot["under"].append(pr)
        if not (h2h_home and h2h_draw and h2h_away):
            continue  # ohne 1X2 kein verwertbarer Datensatz
        tot_list = []
        for pt in sorted(totals):
            o, u = totals[pt]["over"], totals[pt]["under"]
            if o and u:
                tot_list.append({"point": pt,
                                 "over": round(median(o), 3),
                                 "under": round(median(u), 3),
                                 "n": min(len(o), len(u))})
        matches.append({
            "commence": ev.get("commence_time"),
            "home": home,
            "away": away,
            "n_books": len(h2h_home),
            "h2h": {"home": round(median(h2h_home), 3),
                    "draw": round(median(h2h_draw), 3),
                    "away": round(median(h2h_away), 3)},
            "totals": tot_list,
        })

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sport": SPORT,
        "source": "the-odds-api.com - Konsens (Median) mehrerer Buchmacher",
        "n_matches": len(matches),
        "matches": matches,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("OK: %d Spiele -> %s" % (len(matches), OUT))
    if remaining is not None:
        print("Odds-API-Kontingent: %s verbraucht, %s uebrig" % (used, remaining))
    return 0


if __name__ == "__main__":
    sys.exit(main())
