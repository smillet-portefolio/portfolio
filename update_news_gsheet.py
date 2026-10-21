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
    elif "--write" in sys.argv: write(sys.argv[sys.argv.index("--write") + 1])
    else: print(__doc__ or "usage: --holdings | --write file.json")
