# Historique des dividendes par action + calendrier des publications (Yahoo Finance)
# -> onglet "Dividends_Cal" du Google Sheet, lu par le dashboard :
#    • 💸 Dividendes › 📅 Projections : dividendes estimés des 12 prochains mois (positions détenues × derniers dividendes)
#    • 📰 Infos › 📅 Prochaines publications : dernière et prochaine publication de résultats (confirmée Yahoo ou estimée)
#   python update_dividends_gsheet.py            -> met à jour l'onglet (n'écrit RIEN dans l'onglet Data)
#   python update_dividends_gsheet.py --dry-run  -> affiche seulement
import datetime, json, statistics, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import yfinance as yf

from update_news_gsheet import svc, SHEET_ID, CHUNK
from update_prix_gsheet import YS_OVERRIDE, VAR_OVERRIDE

TAB = "Dividends_Cal"
DRY = "--dry-run" in sys.argv
TODAY = datetime.date.today()


def held():
    """Titres détenus : actions + ETF de Seb, actions des enfants (ticker -> {name, isin, kind})."""
    rows = svc().values().get(spreadsheetId=SHEET_ID, range="Data!A:ZZ").execute().get("values", [])
    d = {r[0]: "".join(r[1:]) for r in rows if r}
    out = {}
    for r in json.loads(d.get("book2_all_rows") or "[]"):
        if r.get("typeInv") in ("Action", "ETF") and float(r.get("qty") or 0) > 0 and r.get("ticker"):
            out.setdefault(r["ticker"], {"name": r.get("name"), "isin": r.get("isin"), "kind": r.get("typeInv")})
    for r in json.loads(d.get("kids_hold") or "[]"):
        if r.get("t") == "Action" and float(r.get("qty") or 0) > 0 and r.get("ticker"):
            out.setdefault(r["ticker"], {"name": r.get("nom"), "isin": r.get("isin"), "kind": "Action"})
    return out


def _d(x):
    try: return x.date() if hasattr(x, "date") else datetime.date.fromisoformat(str(x)[:10])
    except Exception: return None


def fetch(ticker):
    sym = VAR_OVERRIDE.get(ticker) or YS_OVERRIDE.get(ticker) or ticker   # CATL.VI -> 3750.HK (dividendes en HKD)
    t = yf.Ticker(sym)
    res = {"ysym": sym}
    try: cur = t.fast_info.currency
    except Exception: cur = None
    k = 0.01 if cur in ("GBp", "GBX") else 1.0                            # pence -> livres
    res["currency"] = "GBP" if cur in ("GBp", "GBX") else (cur or "EUR")
    try:
        dv = t.dividends
        start = TODAY - datetime.timedelta(days=3 * 366)
        res["divs"] = [[str(i.date()), round(float(v) * k, 6)] for i, v in dv.items() if i.date() >= start and float(v) > 0]
    except Exception:
        res["divs"] = []
    cal = {}
    try: cal = t.calendar or {}
    except Exception: pass
    ex = _d(cal.get("Ex-Dividend Date")) if cal.get("Ex-Dividend Date") else None
    if ex and ex >= TODAY: res["next_ex"] = str(ex)
    pay = _d(cal.get("Dividend Date")) if cal.get("Dividend Date") else None
    if pay and pay >= TODAY: res["next_pay"] = str(pay)
    # Publications de résultats : historique + prochaines dates connues de Yahoo
    dates = set()
    for x in (cal.get("Earnings Date") or []):
        if _d(x): dates.add(_d(x))
    try:
        ed = t.get_earnings_dates(limit=12)
        if ed is not None:
            for i in ed.index: dates.add(i.date())
    except Exception:
        pass
    past = sorted(x for x in dates if x < TODAY)
    fut = sorted(x for x in dates if x >= TODAY)
    if past: res["last_earn"] = str(past[-1])
    if fut:
        res["next_earn"], res["next_earn_src"] = str(fut[0]), "yahoo"
    elif past:
        gaps = [(b - a).days for a, b in zip(past[-5:], past[-4:]) if 60 <= (b - a).days <= 200]
        gap = int(statistics.median(gaps)) if gaps else 91
        nxt = past[-1] + datetime.timedelta(days=gap)
        while nxt < TODAY: nxt += datetime.timedelta(days=gap)
        res["next_earn"], res["next_earn_src"] = str(nxt), "estimee"
    return res


def fx_rates(currencies):
    out = {"EUR": 1.0}
    for c in currencies:
        if c in out: continue
        try: out[c] = float(yf.Ticker(f"{c}EUR=X").fast_info.last_price)
        except Exception: pass
    return out


def main():
    h = held()
    items = {}
    for tk, meta in h.items():
        try:
            r = fetch(tk); r.update(meta); items[tk] = r
            print(f"  {tk:<10} {r['ysym']:<9} {r['currency']:<4} divs={len(r['divs'])} next_ex={r.get('next_ex','-')} "
                  f"last_earn={r.get('last_earn','-')} next_earn={r.get('next_earn','-')} ({r.get('next_earn_src','-')})")
        except Exception as e:
            print(f"  {tk}: erreur {e}")
    data = {"generated_at": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
            "fx": fx_rates({r["currency"] for r in items.values()}), "items": items}
    if DRY:
        print(json.dumps(data["fx"])); return
    s = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    api = svc(write=True)
    try: api.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}).execute()
    except Exception: pass
    api.values().clear(spreadsheetId=SHEET_ID, range=f"{TAB}!A:ZZ").execute()
    api.values().update(spreadsheetId=SHEET_ID, range=f"{TAB}!A1", valueInputOption="RAW",
                        body={"values": [["generated_at", data["generated_at"]], ["json"] + [s[i:i + CHUNK] for i in range(0, len(s), CHUNK)]]}).execute()
    print(f"✅ Onglet {TAB} mis à jour ({len(items)} titres)")


if __name__ == "__main__":
    main()
