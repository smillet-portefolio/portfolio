# Infos quotidiennes des actions détenues -> onglet "News" du Google Sheet (lu par l'onglet 📰 Infos du dashboard)
#   python update_news_gsheet.py --holdings          -> affiche (JSON) les actions détenues : portefeuille + enfants
#   python update_news_gsheet.py --write news.json   -> écrit le résumé dans l'onglet News (n'écrit RIEN dans l'onglet Data)
import json, os, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA = r"C:\Users\smill\OneDrive\Documents\banque\bourse\service_account.json"
SHEET_ID = "15w4s6chCytFKmPSpGXeYQ9fiJEVD_T5U9671Q0chn_Q"
TAB = "News"
CHUNK = 45000


def svc(write=False):
    scope = "https://www.googleapis.com/auth/spreadsheets" + ("" if write else ".readonly")
    sa_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT")          # GitHub Actions (secret)
    if sa_env:
        creds = service_account.Credentials.from_service_account_info(json.loads(sa_env), scopes=[scope])
    else:                                                       # exécution locale
        creds = service_account.Credentials.from_service_account_file(SA, scopes=[scope])
    return build("sheets", "v4", credentials=creds).spreadsheets()


# Thèmes de marché des ETF / fonds détenus (ISIN -> clé de thème). Un ETF absent de la table va dans "other".
ETF_THEMES = [
    ("world",    "🌐 Actions mondiales",          "MSCI World, MSCI ACWI, FTSE All-World (dividendes) : marchés actions mondiaux, Fed, résultats des grandes capitalisations"),
    ("us",       "🗽 Actions américaines",        "S&P 500, actions US : Wall Street, Fed, inflation US, saison des résultats, grandes valeurs tech"),
    ("europe",   "💶 Actions européennes",        "Euro Stoxx 50, Stoxx Europe 600 : BCE, croissance européenne, CAC 40 / DAX"),
    ("em",       "🌏 Émergents hors Chine",       "MSCI Emerging Markets ex China : Inde, Taïwan, Corée, Brésil, dollar, flux vers les émergents"),
    ("eeurope",  "🧭 Europe de l'Est",            "MSCI Eastern Europe ex Russia : Pologne, Hongrie, Tchéquie, Ukraine, fonds européens"),
    ("greece",   "🏛️ Grèce",                      "MSCI Greece : bourse d'Athènes, banques grecques, note souveraine"),
    ("brazil",   "🌎 Brésil",                     "MSCI Brazil : Bovespa, real, Petrobras, Vale, banques, banque centrale du Brésil"),
    ("clean",    "♻️ Énergie propre",             "Global Clean Energy : solaire, éolien, hydrogène, politiques climatiques, taux"),
    ("uranium",  "☢️ Uranium & nucléaire",         "Uranium & nucléaire : prix de l'uranium, Cameco, Kazatomprom, nouveaux réacteurs, SMR"),
    ("other",    "📦 Autres ETF",                  "Autres ETF"),
]
ETF_THEME_BY_ISIN = {
    "IE000BI8OT95": "world", "IE00BJ0KDQ92": "world", "IE00B4L5Y983": "world", "IE00B6R52259": "world", "IE00BK5BR626": "world",
    "IE00BMTX1Y45": "us", "IE00B03HCW31": "us",
    "LU0908500753": "europe", "FR0007054358": "europe",
    "LU2009202107": "em", "IE00BMG6Z448": "em",
    "LU1900066462": "eeurope", "FR0010405431": "greece",
    "LU0292109344": "brazil", "DE000A0Q4R85": "brazil",
    "IE00B1XNHC34": "clean", "IE000U58J0M1": "clean",
    "IE000M7V94E1": "uranium",
}


def etf_themes(as_list=False):
    rows = svc().values().get(spreadsheetId=SHEET_ID, range="Data!A:ZZ").execute().get("values", [])
    d = {r[0]: "".join(r[1:]) for r in rows if r}
    etfs = {}
    for r in json.loads(d.get("book2_all_rows") or "[]"):
        if r.get("typeInv") != "ETF" or float(r.get("qty") or 0) <= 0: continue
        e = etfs.setdefault((r.get("isin") or r.get("ticker") or "").upper(),
                            {"name": r.get("name"), "ticker": r.get("ticker"), "isin": r.get("isin"), "owner": []})
        if "Seb" not in e["owner"]: e["owner"].append("Seb")
    for r in json.loads(d.get("kids_hold") or "[]"):
        if r.get("t") not in ("ETF", "Fonds") or float(r.get("qty") or 0) <= 0: continue
        e = etfs.setdefault((r.get("isin") or r.get("ticker") or "").upper(),
                            {"name": r.get("nom"), "ticker": r.get("ticker"), "isin": r.get("isin"), "owner": []})
        if r.get("e") and r.get("e") not in e["owner"]: e["owner"].append(r.get("e"))
    out = []
    for key, label, scope in ETF_THEMES:
        lst = [e for k, e in etfs.items() if ETF_THEME_BY_ISIN.get((e["isin"] or "").upper(), "other") == key]
        if lst: out.append({"key": key, "label": label, "scope": scope, "etfs": sorted(lst, key=lambda x: x["name"] or "")})
    if as_list: return out
    print(json.dumps(out, ensure_ascii=False, indent=1))


def holdings(as_list=False):
    rows = svc().values().get(spreadsheetId=SHEET_ID, range="Data!A:ZZ").execute().get("values", [])
    d = {r[0]: "".join(r[1:]) for r in rows if r}
    out = {}
    for r in json.loads(d.get("book2_all_rows") or "[]"):
        if r.get("typeInv") not in ("Action", "Crypto") or float(r.get("qty") or 0) <= 0: continue
        k = (r.get("isin") or r.get("ticker") or "").upper()
        o = out.setdefault(k, {"name": r.get("name"), "ticker": r.get("ticker"), "isin": r.get("isin"),
                               "kind": "crypto" if r.get("typeInv") == "Crypto" else "action", "owner": []})
        if "Seb" not in o["owner"]: o["owner"].append("Seb")
    for r in json.loads(d.get("kids_hold") or "[]"):
        if r.get("t") != "Action" or float(r.get("qty") or 0) <= 0: continue
        k = (r.get("isin") or r.get("ticker") or "").upper()
        o = out.setdefault(k, {"name": r.get("nom"), "ticker": r.get("ticker"), "isin": r.get("isin"), "kind": "action", "owner": []})
        if r.get("e") and r.get("e") not in o["owner"]: o["owner"].append(r.get("e"))
    lst = sorted(out.values(), key=lambda x: (x["kind"], (x["name"] or "").lower()))
    if as_list: return lst
    print(json.dumps(lst, ensure_ascii=False, indent=1))


def write(path=None, data=None):
    if data is None: data = json.load(open(path, encoding="utf-8"))
    data.setdefault("generated_at", datetime.datetime.now().astimezone().isoformat(timespec="minutes"))
    s = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    api = svc(write=True)
    try:
        api.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}).execute()
    except Exception:
        pass  # l'onglet existe déjà
    api.values().clear(spreadsheetId=SHEET_ID, range=f"{TAB}!A:ZZ").execute()
    vals = [["generated_at", data["generated_at"]], ["json"] + [s[i:i + CHUNK] for i in range(0, len(s), CHUNK)]]
    api.values().update(spreadsheetId=SHEET_ID, range=f"{TAB}!A1", valueInputOption="RAW",
                        body={"values": vals}).execute()
    print(f"✅ Onglet {TAB} mis à jour ({len(data.get('stocks', []))} actions, {len(s)} caractères)")


def should_run():
    """Affiche true/false : l'édition du créneau en cours (matin dès 7h00, soir dès 18h30, Prague) reste-t-elle à faire ?
    Permet de rattraper un déclenchement GitHub en retard sans jamais faire deux éditions par créneau."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Prague")
    now = datetime.datetime.now(tz)
    if now.weekday() >= 5: print("false"); return                       # week-end
    m_start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    e_start = now.replace(hour=18, minute=30, second=0, microsecond=0)
    slot = e_start if now >= e_start else (m_start if now >= m_start else None)
    if slot is None: print("false"); return                              # avant 7h00
    last = None
    try:
        v = svc().values().get(spreadsheetId=SHEET_ID, range=f"{TAB}!A1:B1").execute().get("values", [])
        if v and len(v[0]) > 1: last = datetime.datetime.fromisoformat(v[0][1]).astimezone(tz)
    except Exception:
        pass
    print("true" if (last is None or last < slot) else "false")


if __name__ == "__main__":
    if "--should-run" in sys.argv: should_run()
    elif "--holdings" in sys.argv: holdings()
    elif "--etf-themes" in sys.argv: etf_themes()
    elif "--write" in sys.argv: write(sys.argv[sys.argv.index("--write") + 1])
    else: print(__doc__ or "usage: --holdings | --write file.json")
