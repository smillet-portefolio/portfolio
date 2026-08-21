#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_conseq_nav_hist.py
=========================
Maintient l'historique des valeurs de part (VL) des fonds de retraite Conseq et
en dérive l'historique MENSUEL embarqué dans dashboard_portefeuille.html
(const CSQ_NAV_HIST).

Modèle (demande utilisateur) :
  1. À chaque exécution (quotidienne), on lit la VL PUBLIÉE du jour de chaque fonds
     sur sa page publique : « Aktuální hodnota penzijní jednotky: X CZK (D. M. YYYY) ».
  2. On la range dans un HISTORIQUE DATÉ persistant  ->  conseq_nav_daily.json
        { "GLAK": { "2026-07-28": 3.5053, "2026-08-04": 3.6275, ... }, ... }
     Clé = date PUBLIÉE. La VL Conseq ne bouge qu'~1×/semaine : ré-écrire la même
     date/valeur est sans effet, l'historique ne grossit qu'aux vrais changements.
  3. On DÉRIVE la VL mensuelle = valeur à la DERNIÈRE DATE connue de chaque mois,
     et on l'écrit dans CSQ_NAV_HIST[fonds]["YYYY-MM"] (clôture de fin de mois).
     Les mois antérieurs à l'historique daté restent inchangés dans le HTML.
  Idempotent : ne réécrit HTML / JSON que si quelque chose a changé.

Backfill manuel d'une observation datée :
    python update_conseq_nav_hist.py --set GLAK:2026-07-28:3.5053 DL:2026-07-28:1.4534

Prérequis : pip install requests
"""

import re
import os
import sys
import json
import argparse
import datetime

try:
    import requests
except ImportError:
    requests = None

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_FILE  = os.path.join(HERE, "dashboard_portefeuille.html")
DAILY_FILE = os.path.join(HERE, "conseq_nav_daily.json")

BASE = "https://www.conseq.cz/penze/prehled-ucastnickych-fondu/"

# (code interne dans CSQ_NAV_HIST, slug de la page publique)
FUNDS = [
    ("GLAK", "conseq-globalni-akciovy-ucastnicky-fond"),
    ("RAF",  "conseq-realitni-ucastnicky-fond"),
    ("DL",   "conseq-dluhopisovy-ucastnicky-fond"),
    # BOND35 : entièrement vendu (0 unité) -> non suivi.
]

HEADERS = {"User-Agent": "Mozilla/5.0 (update_conseq_nav_hist.py)"}

# « Aktuální hodnota penzijní jednotky: 3,6275 CZK (4. 8. 2026) »
PAT = re.compile(
    r"Aktu[aá]ln[ií]\s+hodnota\s+penzijn[ií]\s+jednotky[:\s]*"
    r"([\d\s ]+,\d+)\s*CZK\s*\(\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*\)",
    re.IGNORECASE,
)


def to_float(s):
    return float(s.replace(" ", "").replace(" ", "").replace(",", "."))


def fetch_nav(slug):
    """Renvoie (valeur_float, 'YYYY-MM-DD') pour un fonds, ou (None, None)."""
    if requests is None:
        raise SystemExit("Installez requests :  pip install requests")
    r = requests.get(BASE + slug, headers=HEADERS, timeout=25)
    r.raise_for_status()
    m = PAT.search(r.text)
    if not m:
        return None, None
    nav = round(to_float(m.group(1)), 4)
    d, mo, y = int(m.group(2)), int(m.group(3)), int(m.group(4))
    return nav, f"{y:04d}-{mo:02d}-{d:02d}"


# ------------------------------------------------------------- historique daté

def load_daily():
    if os.path.exists(DAILY_FILE):
        return json.load(open(DAILY_FILE, encoding="utf-8"))
    return {}


def record_obs(daily, code, ymd, val):
    """Ajoute une observation datée. Renvoie True si l'historique a changé."""
    val = round(float(val), 4)
    d = daily.setdefault(code, {})
    if d.get(ymd) is None or abs(float(d[ymd]) - val) > 1e-9:
        d[ymd] = val
        return True
    return False


def monthly_from_daily(daily):
    """Dérive {code: {'YYYY-MM': valeur_dernière_date_du_mois}}."""
    out = {}
    for code, series in daily.items():
        by_month = {}
        for ymd, val in series.items():
            ym = ymd[:7]
            # garde la valeur de la DATE la plus tardive du mois
            if ym not in by_month or ymd > by_month[ym][0]:
                by_month[ym] = (ymd, round(float(val), 4))
        out[code] = {ym: v for ym, (dd, v) in by_month.items()}
    return out


# -------------------------------------------------------------------- HTML I/O

def load_const(html, name):
    """Renvoie (dict, start, end) du littéral JSON de `const <name>={...}`."""
    i = html.find(name)
    if i < 0:
        raise SystemExit(name + " introuvable dans le HTML")
    j = html.find("{", i)
    obj, endrel = json.JSONDecoder().raw_decode(html[j:])
    return obj, j, j + endrel


def load_nav_hist(html):
    return load_const(html, "CSQ_NAV_HIST")


def merge_weekly(objw, daily):
    """Ajoute les observations datées dans CSQ_NAV_W. Renvoie nb de changements."""
    changed = 0
    for code, series in daily.items():
        tgt = objw.setdefault(code, {})
        for ymd, val in series.items():
            val = round(float(val), 4)
            cur = tgt.get(ymd)
            if cur is None or abs(float(cur) - val) > 1e-9:
                tgt[ymd] = val
                changed += 1
    return changed


def merge_monthly(obj, monthly):
    """Écrit les VL mensuelles dérivées dans CSQ_NAV_HIST. Renvoie nb de changements."""
    changed = 0
    for code, months in monthly.items():
        tgt = obj.setdefault(code, {})
        for ym, val in months.items():
            cur = tgt.get(ym)
            if cur is None or abs(float(cur) - float(val)) > 1e-9:
                print(f"  CSQ_NAV_HIST {code} {ym} : {cur} -> {val}")
                tgt[ym] = val
                changed += 1
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", nargs="*", default=[],
                    help="Observation datée : CODE:YYYY-MM-DD:VALEUR")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    daily = load_daily()
    daily_changed = False

    # 1) observations manuelles éventuelles
    for spec in args.set:
        code, ymd, val = spec.split(":")
        if record_obs(daily, code.strip().upper(), ymd.strip(),
                      float(val.replace(",", "."))):
            daily_changed = True
            print(f"  obs {code} {ymd} = {val}")

    # 2) scrape des VL publiées du jour (sauf si uniquement --set)
    if not args.set:
        print("=" * 60)
        print("  Conseq NAV —", datetime.date.today().isoformat())
        print("=" * 60)
        for code, slug in FUNDS:
            try:
                nav, ymd = fetch_nav(slug)
                if nav is None:
                    print(f"  {code:6s} -> valeur introuvable")
                    continue
                new = record_obs(daily, code, ymd, nav)
                print(f"  {code:6s} {nav:>8.4f} CZK  ({ymd})" + ("  [nouveau]" if new else "  [inchangé]"))
                daily_changed = daily_changed or new
            except Exception as e:
                print(f"  {code:6s} -> erreur : {e}")

    # 3) met à jour le HTML :
    #    - CSQ_NAV_W  = série HEBDO (lue par l'onglet Évolution) -> ajoute les dates
    #    - CSQ_NAV_HIST = série MENSUELLE (legacy) -> dernière valeur de chaque mois
    monthly = monthly_from_daily(daily)
    html = open(HTML_FILE, encoding="utf-8").read()

    # patch CSQ_NAV_W en premier (situé APRÈS CSQ_NAV_HIST -> n'affecte pas ses index)
    w_changed = 0
    if "CSQ_NAV_W" in html:
        objw, sw, ew = load_const(html, "const CSQ_NAV_W")
        w_changed = merge_weekly(objw, daily)
        if w_changed:
            html = html[:sw] + json.dumps(objw, separators=(",", ":")) + html[ew:]

    objm, sm, em = load_nav_hist(html)
    m_changed = merge_monthly(objm, monthly)
    if m_changed:
        html = html[:sm] + json.dumps(objm, separators=(",", ":")) + html[em:]

    html_changed = w_changed + m_changed

    if args.dry_run:
        print(f"[dry-run] daily changé={daily_changed}, hebdo={w_changed}, mensuel={m_changed}")
        return

    if daily_changed:
        json.dump(daily, open(DAILY_FILE, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0, sort_keys=True)
        print(f"Historique daté -> {os.path.basename(DAILY_FILE)}")

    if html_changed:
        if not os.path.exists(HTML_FILE + ".bak"):
            open(HTML_FILE + ".bak", "w", encoding="utf-8").write(
                open(HTML_FILE, encoding="utf-8").read())
        open(HTML_FILE, "w", encoding="utf-8").write(html)
        print(f"HTML mis à jour (hebdo:{w_changed}, mensuel:{m_changed}).")
    else:
        print("HTML : rien à changer.")


if __name__ == "__main__":
    main()
