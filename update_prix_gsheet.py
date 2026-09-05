#!/usr/bin/env python3
"""
update_prix_gsheet.py
Écrit les prix ET les variations % (1D / 1W / 1M / 3M / 6M / 1Y / YTD)
dans Google Sheets (onglet "Prices") avec décimales complètes.
Inclut aussi les valeurs de part des fonds de retraite Conseq (CONSEQ_GLAK/RAF/DL).
Prérequis : pip install yfinance pandas requests google-auth google-api-python-client
"""

import datetime
import os
import sys
import json
import re
import requests
import pandas as pd
import yfinance as yf

# Windows : la console (cp1250) ne sait pas afficher « à », « → », « ✅ »… ce qui
# faisait planter le script AU DÉMARRAGE (UnicodeEncodeError) avant toute mise à
# jour des prix. On force la sortie en UTF-8 pour que les print ne plantent plus.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SERVICE_ACCOUNT_FILE = r"C:\Users\smill\OneDrive\Documents\banque\bourse\service_account.json"
SHEET_ID  = os.environ.get("SHEET_ID", "15w4s6chCytFKmPSpGXeYQ9fiJEVD_T5U9671Q0chn_Q")
SHEET_TAB = "Prices"
HIST_TAB  = "Historique_Prix"        # onglet historique quotidien (Date|Ticker|Close_EUR)
PORTFOLIO_EUR_CLOSES = {}            # {ticker: close_eur} rempli par collecter_prix()
CONSEQ_HIST_OBS = {}                 # {tick: (date_publiee 'YYYY-MM-DD', nav CZK)} -> Historique_Prix

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_OK = True
except ImportError:
    print("pip install google-auth google-api-python-client")
    GOOGLE_OK = False

# (ticker interne, nom, devise, symbole Yahoo pour l'historique des variations)
TICKERS = [
    ("ABVX.PA",  "Abivax",                        "EUR", "ABVX.PA"),
    ("FGR.PA",   "Eiffage",                       "EUR", "FGR.PA"),
    ("VIE.PA",   "Vonovia",                       "EUR", "VIE.PA"),
    ("DTE.DE",   "Deutsche Telekom",              "EUR", "DTE.DE"),
    ("EL.PA",    "EssilorLuxottica",              "EUR", "EL.PA"),
    ("RACE.MI",  "Ferrari",                       "EUR", "RACE.MI"),
    ("IDL.PA",   "ID Logistics",                  "EUR", "IDL.PA"),
    ("IFX.DE",   "Infineon",                      "EUR", "IFX.DE"),
    ("ENR.DE",   "Siemens Energy",                "EUR", "ENR.DE"),
    ("SGO.PA",   "Saint-Gobain",                  "EUR", "SGO.PA"),
    ("SU.PA",    "Schneider Electric",            "EUR", "SU.PA"),
    ("SAN.MC",   "Banco Santander",               "EUR", "SAN.MC"),
    ("RR.L",     "Rolls-Royce",                   "GBp", "RR.L"),
    ("MSFT",     "Microsoft",                     "USD", "MSFT"),
    ("ORCL",     "Oracle",                        "USD", "ORCL"),
    ("VST",      "Vistra Corp",                   "USD", "VST"),
    ("VU.PA",    "Vusion Group",                  "EUR", "VU.PA"),
    ("SPIE.PA",  "Spie",                          "EUR", "SPIE.PA"),
    ("EMXC.DE",  "Amundi MSCI Emerging ex China", "EUR", "EMXC.DE"),
    ("LSMC.DE",  "Amundi MSCI Semiconductors",    "EUR", "LSMC.DE"),
    ("HYDE.DE",  "Invesco Hydrogen Economy",      "EUR", "HYDE.DE"),
    ("IQQH.DE",  "iShares Global Clean Energy",   "EUR", "IQQH.DE"),
    ("I500.DE",  "iShares S&P 500 Swap",          "EUR", "I500.DE"),
    ("JEDI.DE",  "VanEck Space Innovators",       "EUR", "JEDI.DE"),
    ("NUKL.DE",  "VanEck Uranium & Nuclear",      "EUR", "NUKL.DE"),
    ("XDWD.DE",  "Xtrackers MSCI World",          "EUR", "XDWD.DE"),
    ("XDWH.DE",  "Xtrackers MSCI World Health Care", "EUR", "XDWH.DE"),
    ("MTPI.PA",  "iShares MSCI ex China",         "EUR", "MTPI.PA"),
    ("VGWE.DE",  "Vanguard All-World High Div",   "EUR", "VGWE.DE"),
    # Invesco MSCI World UCITS ETF (Acc) — coté Xetra sous SC0J.DE (zéro, pas la lettre O).
    # L'entrée « SCOJ.DE » sert d'alias : si la ligne du portefeuille est saisie avec un O,
    # YS_OVERRIDE la redirige vers la cotation Yahoo SC0J.DE.
    ("SC0J.DE",  "Invesco MSCI World UCITS ETF",  "EUR", "SC0J.DE"),
    ("SCOJ.DE",  "Invesco MSCI World UCITS ETF",  "EUR", "SC0J.DE"),
    ("IWDA.AS",  "iShares Core MSCI World",       "EUR", "IWDA.AS"),   # détenu par Corentin
    ("Q8Y0",     "iShares Global Clean Energy Transition", "EUR", "Q8Y0.DE"),
    ("MWRE",     "Amundi Core MSCI World",        "EUR", "MWRE.DE"),
    ("C7A0.DE",  "CATL",                          "EUR", "C7A0.MU"),
    ("XMBR.DE",  "Xtrackers MSCI Brazil",         "EUR", "XMBR.DE"),
    ("4BRZ.MI",  "iShares MSCI Brazil",           "EUR", "4BRZ.MI"),
    ("BTC/EUR",  "Bitcoin",                       "EUR", "BTC-EUR"),
    ("ETH/EUR",  "Ethereum",                      "EUR", "ETH-EUR"),
    ("EUR/CZK",  "Euro / Couronne tchèque",       "CZK", "EURCZK=X"),
    ("USD/CZK",  "Dollar / Couronne tchèque",     "CZK", "USDCZK=X"),
    ("GBP/CZK",  "Livre / Couronne tchèque",      "CZK", "GBPCZK=X"),
]

TICKERS_US = {"MSFT", "ORCL", "VST"}

# Colonnes de variations dans l'ordre voulu
VAR_KEYS = ["1D", "1W", "1M", "3M", "6M", "1Y", "YTD"]


def prix_yahoo(ticker):
    try:
        t = yf.Ticker(ticker)
        if ticker in TICKERS_US:
            info = t.info
            p = info.get("currentPrice") or info.get("regularMarketPrice")
            if p and float(p) > 0:
                return float(p)
        p = t.fast_info.last_price
        if p and p > 0:
            return float(p)
    except Exception as e:
        print(f"  [Yahoo {ticker}] {e}")
    return None


def variations_yahoo(yahoo_sym):
    """Retourne {1D,1W,1M,3M,6M,1Y,YTD} en % à partir de l'historique Yahoo."""
    vides = {k: None for k in VAR_KEYS}
    try:
        hist = yf.Ticker(yahoo_sym).history(period="2y", auto_adjust=False)
        if hist.empty:
            return vides
        closes = hist["Close"].dropna()
        if closes.empty:
            return vides

        last = float(closes.iloc[-1])
        ld = closes.index[-1]

        def close_on_or_before(target):
            sub = closes[closes.index <= target]
            return float(sub.iloc[-1]) if not sub.empty else None

        def pct(ref):
            if ref and ref > 0:
                return round((last / ref - 1) * 100, 2)
            return None

        res = dict(vides)
        res["1D"] = pct(float(closes.iloc[-2])) if len(closes) >= 2 else None
        res["1W"] = pct(close_on_or_before(ld - pd.Timedelta(days=7)))
        res["1M"] = pct(close_on_or_before(ld - pd.DateOffset(months=1)))
        res["3M"] = pct(close_on_or_before(ld - pd.DateOffset(months=3)))
        res["6M"] = pct(close_on_or_before(ld - pd.DateOffset(months=6)))
        res["1Y"] = pct(close_on_or_before(ld - pd.DateOffset(years=1)))

        ytd_start = pd.Timestamp(year=ld.year, month=1, day=1, tz=ld.tz)
        prev = closes[closes.index < ytd_start]  # dernier cours de l'an passé
        res["YTD"] = pct(float(prev.iloc[-1])) if not prev.empty else None
        return res
    except Exception as e:
        print(f"  [Var {yahoo_sym}] {e}")
        return vides


def prix_binance(symbole):
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbole}", timeout=10)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        print(f"  [Binance {symbole}] {e}")
    return None


def taux_cnb():
    taux = {}
    try:
        r = requests.get(
            "https://www.cnb.cz/en/financial-markets/foreign-exchange-market"
            "/central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/daily.txt",
            timeout=10)
        r.raise_for_status()
        for ligne in r.text.strip().split("\n")[2:]:
            parts = ligne.split("|")
            if len(parts) < 5:
                continue
            code   = parts[3].strip()
            amount = int(parts[2].strip())
            rate   = float(parts[4].strip().replace(",", ".")) / amount
            if code in ("EUR", "USD", "GBP"):
                taux[code] = rate
    except Exception as e:
        print(f"  [CNB] {e}")
    return taux


# Fonds de retraite Conseq (DPS) — valeur de part publiée sur conseq.cz
# (ticker interne pour l'onglet Prices, nom, slug de la page)
CONSEQ_FUNDS = [
    ("CONSEQ_GLAK", "Conseq globalni akciovy", "conseq-globalni-akciovy-ucastnicky-fond"),
    ("CONSEQ_RAF",  "Conseq realitni",         "conseq-realitni-ucastnicky-fond"),
    ("CONSEQ_DL",   "Conseq dluhopisovy",      "conseq-dluhopisovy-ucastnicky-fond"),
    ("CONSEQ_BOND35", "Conseq Target Bond 2035", "conseq-target-bond-2035-ucastnicky-fond"),
]

_CONSEQ_PAT = re.compile(
    r"Aktu[aá]ln[ií]\s+hodnota\s+penzijn[ií]\s+jednotky[:\s]*"
    r"([\d\s ]+,\d+)\s*CZK\s*\(([^)]+)\)",
    re.IGNORECASE,
)


def prix_conseq(slug):
    """Retourne (valeur_part_CZK, date_str) depuis la page publique du fonds Conseq."""
    try:
        url = "https://www.conseq.cz/penze/prehled-ucastnickych-fondu/" + slug
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = text.replace("\xa0", " ").replace("&nbsp;", " ")
        text = re.sub(r"\s+", " ", text)
        m = re.search(r"hodnota penzijn[ií] jednotky[:\s]*([\d ]+,\d+)\s*CZK\s*\(([^)]+?\d{4})\)", text, re.IGNORECASE)
        if not m:
            return None, None
        nav = float(m.group(1).replace(" ", "").replace(" ", "").replace(",", "."))
        return nav, m.group(2).strip()
    except Exception as e:
        print(f"  [Conseq {slug}] {e}")
        return None, None


def _conseq_date_iso(s):
    """Convertit une date Conseq « 18. 8. 2026 » en ISO « 2026-08-18 »."""
    m = re.match(r"\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", str(s or ""))
    if not m:
        return None
    return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"


def fmt_prix(p):
    """Prix en string a point decimal. Ecrit en RAW -> stocke tel quel (texte),
    aucune conversion locale. Le dashboard lit le prix via parseFloat (sans
    gestion de la virgule) : il FAUT donc garder le point."""
    if p is None:
        return ""
    return repr(p)


def fmt_var(v):
    """Variation en string a point decimal. ECRITE EN RAW : sans RAW (ex.
    USER_ENTERED), Google Sheets en locale tchèque/française interpretait des
    chaines comme '5.9', '11.9', '15.7' comme des DATES (5 sept / 11 sept /
    15 juil) -> valeurs corrompues. RAW = stockage litteral, plus de date."""
    if v is None:
        return ""
    return repr(v)


# Symbole Yahoo quand le ticker interne diffère du symbole Yahoo (ex. Q8Y0 -> Q8Y0.DE)
YS_OVERRIDE = {t: y for (t, n, c, y) in TICKERS if t != y}
# Symbole Yahoo dédié au CALCUL DES VARIATIONS (1D..YTD) quand la cotation utilisée
# pour le prix n'a pas d'historique exploitable. Le prix reste inchangé ; seules les
# variations % (indépendantes de la devise) sont lues sur ce symbole.
# CATL (C7A0.DE/.MU en EUR) : cotation secondaire européenne récente, sans historique
# Yahoo -> on lit les variations sur la ligne H de Hong Kong 3750.HK.
VAR_OVERRIDE = {
    "C7A0.DE": "3750.HK",
}
# Tickers internes "non actions" (crypto / FX) gérés en statique
STATIC_TICKS = {"BTC/EUR", "ETH/EUR", "EUR/CZK", "USD/CZK", "GBP/CZK"}
# Produits à prix MANUEL (épargne / structurés) — non cotés sur Yahoo, on les saute
SKIP_TICKS = {"CASH3.5"}


def _get_creds():
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    sa_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if sa_env:
        return service_account.Credentials.from_service_account_info(json.loads(sa_env), scopes=SCOPES)
    return service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)


def lire_holdings_sheet():
    """Lit les positions actuelles depuis l'onglet Data (clé book2_all_rows)."""
    if not GOOGLE_OK:
        return None
    try:
        svc = build("sheets", "v4", credentials=_get_creds()).spreadsheets()
        res = svc.values().get(spreadsheetId=SHEET_ID, range="Data!A:Z").execute()
        data = {}
        for r in (res.get("values", []) or []):
            if r and r[0]:
                data[r[0]] = "".join(r[1:])   # recoller les morceaux (chunks 45000)
        rows = []
        for key in ("book2_all_rows", "book2_extra_rows"):
            raw = data.get(key)
            if raw:
                try:
                    lst = json.loads(raw)
                    if isinstance(lst, list):
                        rows += lst
                except Exception:
                    pass
        return rows or None
    except Exception as e:
        print(f"  [Data] lecture portefeuille impossible : {e}")
        return None


def prix_devise_yahoo(ticker):
    """Retourne (prix, devise) depuis Yahoo (devise = monnaie de cotation réelle)."""
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        cur = None
        try:
            cur = fi.currency
        except Exception:
            cur = None
        prix = None
        try:
            lp = fi.last_price
            if lp and lp > 0:
                prix = float(lp)
        except Exception:
            pass
        if prix is None:
            info = t.info
            p = info.get("currentPrice") or info.get("regularMarketPrice")
            prix = float(p) if p else None
            if not cur:
                cur = info.get("currency")
        return prix, cur
    except Exception as e:
        print(f"  [Yahoo {ticker}] {e}")
        return None, None


def tickers_portefeuille():
    """Liste DYNAMIQUE [(ticker, nom)] des actions/ETF détenus (hors crypto/FX).
    Source : positions actuelles du dashboard (book2_all_rows). Les titres vendus
    n'y figurant plus sont automatiquement exclus. Renvoie None si indisponible."""
    hold = lire_holdings_sheet()
    if not hold:
        return None
    CRYPTO_BROKERS = {"ledger", "binance"}
    seen = {}
    for r in hold:
        if not isinstance(r, dict):
            continue
        tk = (r.get("ticker") or "").strip()
        if not tk or tk in STATIC_TICKS:
            continue
        if tk.upper() in SKIP_TICKS:
            continue
        br = (r.get("broker") or "").strip().lower()
        ty = (r.get("typeInv") or "").strip().lower()
        if br in CRYPTO_BROKERS or "crypto" in ty:
            continue
        if re.search(r"structur|épargn|epargn|livret", ty):  # produits prix manuel
            continue
        if tk not in seen:
            seen[tk] = (r.get("name") or tk)
    return [(tk, nm) for tk, nm in seen.items()]


ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def tickers_enfants():
    """Liste [(cle, nom)] des lignes enfants (kids_hold) detenues avec un ticker
    OU un ISIN. Cle = ticker si present, sinon ISIN. Exclut les fonds euro / cash /
    monetaire SANS ticker (Netissima, Eurossima... mis a jour manuellement)."""
    if not GOOGLE_OK:
        return []
    try:
        svc = build("sheets", "v4", credentials=_get_creds()).spreadsheets()
        res = svc.values().get(spreadsheetId=SHEET_ID, range="Data!A:Z").execute()
        data = {}
        for r in (res.get("values", []) or []):
            if r and r[0]:
                data[r[0]] = "".join(r[1:])
        raw = data.get("kids_hold")
        hold = json.loads(raw) if raw else []
    except Exception as e:
        print(f"  [Data] kids_hold indisponible : {e}")
        return []
    seen = {}
    for h in (hold or []):
        if not isinstance(h, dict):
            continue
        tk = (h.get("ticker") or "").strip()
        isin = (h.get("isin") or "").strip().upper()
        ty = (h.get("t") or "").strip().lower()
        # Fonds euro / cash / monetaire sans ticker : prix manuel -> ignore
        if not tk and re.search(r"fonds ?€|euro|cash|monét|monet|livret", ty):
            continue
        key = tk if tk else isin
        if not key or key in STATIC_TICKS or key.upper() in SKIP_TICKS:
            continue
        if key not in seen:
            seen[key] = (h.get("nom") or key)
    return [(k, n) for k, n in seen.items()]


# Correspondances ISIN -> ticker Yahoo forcees (priorite sur la recherche automatique)
ENFANTS_ISIN_OVERRIDE = {
    "IE00BMG6Z448": "MTPI.PA",   # iShares MSCI EM ex-China -> cotation Euronext Paris (EUR)
    "DE000A0Q4R85": "4BRZ.MI",   # iShares MSCI Brazil -> Borsa Italiana (EUR)
    "IE00B4L5Y983": "IWDA.AS",   # iShares Core MSCI World -> Euronext Amsterdam (EUR) — Corentin
}


def resolve_isin(isin):
    """Resout un ISIN en (symbole Yahoo, prix, devise). Utilise d'abord une
    correspondance forcee (ENFANTS_ISIN_OVERRIDE), sinon l'endpoint de recherche Yahoo."""
    ov = ENFANTS_ISIN_OVERRIDE.get((isin or "").upper())
    if ov:
        p, c = prix_devise_yahoo(ov)
        if p and p > 0:
            print(f"    [isin->override] {isin} -> {ov} ({c})")
            return ov, p, c
    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        r = requests.get(url, params={"q": isin, "quotesCount": 5, "newsCount": 0},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        quotes = (r.json() or {}).get("quotes") or []
        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue
            p, c = prix_devise_yahoo(sym)
            if p and p > 0:
                print(f"    [isin] {isin} -> {sym} ({c})")
                return sym, p, c
        return isin, None, None
    except Exception as e:
        print(f"  [ISIN {isin}] {e}")
        return isin, None, None


_YS_SUFFIXES = ["", ".DE", ".MI", ".PA", ".AS", ".L", ".SW", ".F"]
def resolve_yahoo(tick):
    """Repli multi-place : pour un ticker sans suffixe (nouvel ETF/action europeen
    ajoute au portefeuille), essaie les principales bourses et renvoie
    (symbole, prix, devise) au premier resultat valide. Sinon (tick, None, None)."""
    if any(c in tick for c in (".", "-", "=")):
        p, c = prix_devise_yahoo(tick)
        return tick, p, c
    for suf in _YS_SUFFIXES:
        sym = tick + suf
        p, c = prix_devise_yahoo(sym)
        if p and p > 0:
            if suf:
                print(f"    [resolve] {tick} -> {sym} ({c})")
            return sym, p, c
    return tick, None, None


def collecter_prix():
    print("\n--- Taux CNB ---")
    cnb = taux_cnb()
    for devise, val in cnb.items():
        print(f"  OK {devise}/CZK -> {val}")

    print("\n--- Crypto Binance ---")
    # Binance bloque les IP de GitHub (erreur 451) -> repli sur Yahoo Finance.
    btc = prix_binance("BTCEUR") or prix_yahoo("BTC-EUR")
    eth = prix_binance("ETHEUR") or prix_yahoo("ETH-EUR")
    print(f"  {'OK' if btc else 'KO'} Bitcoin  -> {btc}")
    print(f"  {'OK' if eth else 'KO'} Ethereum -> {eth}")
    # Historique quotidien : stocker aussi le close EUR du BTC / ETH (deja en EUR).
    # Cle = ticker des positions du dashboard ("BTC/EUR" / "ETH/EUR", cf onglet Prices).
    if btc and btc > 0: PORTFOLIO_EUR_CLOSES["BTC/EUR"] = round(float(btc), 4)
    if eth and eth > 0: PORTFOLIO_EUR_CLOSES["ETH/EUR"] = round(float(eth), 4)

    maintenant = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = ["Ticker", "Nom", "price last closure", "currency", "Last Update"] + VAR_KEYS
    rows = [header]

    # --- Crypto + FX : STATIQUES (comme aujourd'hui) -------------------------
    STAT = [
        ("BTC/EUR", "Bitcoin",                   btc,          "EUR", "BTC-EUR"),
        ("ETH/EUR", "Ethereum",                  eth,          "EUR", "ETH-EUR"),
        ("EUR/CZK", "Euro / Couronne tchèque",   cnb.get("EUR"), "CZK", "EURCZK=X"),
        ("USD/CZK", "Dollar / Couronne tchèque", cnb.get("USD"), "CZK", "USDCZK=X"),
        ("GBP/CZK", "Livre / Couronne tchèque",  cnb.get("GBP"), "CZK", "GBPCZK=X"),
    ]
    print("\n--- Crypto / FX (statique) ---")
    for tick, nom, prix, cur, ysym in STAT:
        var = variations_yahoo(ysym)
        print(f"  {'OK' if prix else 'KO'} {nom:<40s} ({tick}) -> {prix}")
        rows.append([tick, nom, fmt_prix(prix), cur, maintenant if prix else ""]
                    + [fmt_var(var[k]) for k in VAR_KEYS])

    # --- Actions / ETF : liste DYNAMIQUE depuis le portefeuille --------------
    dyn = tickers_portefeuille()
    if dyn is None:
        print("\n--- Actions/ETF : portefeuille indisponible -> liste statique de secours ---")
        dyn = [(t, n) for (t, n, c, y) in TICKERS if t not in STATIC_TICKS]
    else:
        print(f"\n--- Actions / ETFs du portefeuille ({len(dyn)} tickers, DYNAMIQUE) ---")
    # Ajouter les lignes enfants (ticker OU ISIN) non deja presentes, cle = ticker sinon ISIN
    enfants = tickers_enfants()
    if enfants:
        _existants = {t for (t, _) in dyn}
        _ajoutes = 0
        for k, n in enfants:
            if k not in _existants:
                dyn.append((k, n))
                _existants.add(k)
                _ajoutes += 1
        print(f"--- Enfants (Éditer) : {_ajoutes} tickers/ISIN ajoutés au feed quotidien ---")
    for tick, nom in sorted(dyn, key=lambda x: x[0]):
        ov = YS_OVERRIDE.get(tick)
        if ov:
            ysym = ov                               # override explicite (ex. Q8Y0 -> Q8Y0.DE)
            prix, cur = prix_devise_yahoo(ysym)
        elif ISIN_RE.match(tick):
            ysym, prix, cur = resolve_isin(tick)    # ligne enfant sans ticker -> resolution ISIN
        else:
            ysym, prix, cur = resolve_yahoo(tick)   # repli multi-place automatique
        if not cur:
            cur = "EUR"
        vsym = VAR_OVERRIDE.get(tick, ysym)     # variations depuis une cotation à historique
        var = variations_yahoo(vsym)
        print(f"  {'OK' if prix else 'KO'} {str(nom)[:40]:<40s} ({tick}) -> {prix} [{cur}]"
              + (f"  var<-{vsym}" if vsym != ysym else ""))
        if prix and prix > 0:
            _e = _native_to_eur(prix, cur, cnb)
            if _e and _e > 0:
                PORTFOLIO_EUR_CLOSES[tick] = round(_e, 4)
        rows.append([tick, nom, fmt_prix(prix), cur, maintenant if prix else ""]
                    + [fmt_var(var[k]) for k in VAR_KEYS])

    print("\n--- Conseq (fonds retraite) ---")
    for tick, nom, slug in CONSEQ_FUNDS:
        nav, ddate = prix_conseq(slug)
        print(f"  {'OK' if nav else 'KO'} {nom:<40s} ({tick}) -> {nav}  ({ddate})")
        # Historique DATÉ des VL Conseq (par date publiée) -> onglet Historique_Prix.
        # Le dashboard fusionne ces points dans l'évolution Conseq : dès qu'une VL change,
        # une nouvelle ligne d'évolution apparaît automatiquement (plus de script séparé).
        if nav and nav > 0 and ddate:
            _iso = _conseq_date_iso(ddate)   # « 18. 8. 2026 » -> « 2026-08-18 » (clé Historique_Prix)
            if _iso:
                CONSEQ_HIST_OBS[tick] = (_iso, round(float(nav), 4))
        rows.append(
            [tick, nom + (f" ({ddate})" if ddate else ""), fmt_prix(nav), "CZK",
             (maintenant if nav else "")]
            + ["" for _ in VAR_KEYS]
        )

    return rows


def ecrire_google_sheets(rows):
    if not GOOGLE_OK:
        print("❌ Modules Google manquants")
        return False
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
        sa_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
        if sa_env:  # exécution cloud (GitHub Actions) : identifiants dans une variable/secret
            creds = service_account.Credentials.from_service_account_info(
                json.loads(sa_env), scopes=SCOPES)
        else:       # exécution locale : fichier service_account.json
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build("sheets", "v4", credentials=creds)
        sheet   = service.spreadsheets()

        meta = sheet.get(spreadsheetId=SHEET_ID).execute()
        tabs = [s["properties"]["title"] for s in meta["sheets"]]
        if SHEET_TAB not in tabs:
            sheet.batchUpdate(spreadsheetId=SHEET_ID, body={
                "requests": [{"addSheet": {"properties": {"title": SHEET_TAB}}}]
            }).execute()
            print(f"  Onglet '{SHEET_TAB}' créé")

        sheet.values().clear(spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!A:Z").execute()
        sheet.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_TAB}!A1",
            valueInputOption="RAW",
            body={"values": rows}
        ).execute()
        print(f"\n  ✅ {len(rows)-1} lignes (prix + variations) écrites")
        return True

    except FileNotFoundError:
        print(f"\n  ❌ Fichier introuvable : {SERVICE_ACCOUNT_FILE}")
        return False
    except Exception as e:
        print(f"\n  ❌ Erreur : {e}")
        return False


def _native_to_eur(prix, cur, cnb):
    """Convertit un prix natif en EUR via les taux CNB (CZK par unite)."""
    try:
        cur = (cur or "EUR").strip()
        eur = cnb.get("EUR")
        if cur in ("", "EUR"):
            return prix
        if not eur:
            return None
        if cur == "USD" and cnb.get("USD"):
            return prix * cnb["USD"] / eur
        if cur == "GBP" and cnb.get("GBP"):
            return prix * cnb["GBP"] / eur
        if cur in ("GBp", "GBX") and cnb.get("GBP"):
            return (prix / 100.0) * cnb["GBP"] / eur
        if cur == "CZK":
            return prix / eur
    except Exception:
        pass
    return None


def append_price_history():
    """Enregistre le close EUR du jour de chaque titre du portefeuille dans
    l'onglet Historique_Prix (format long Date|Ticker|Close_EUR). Upsert : une
    seule valeur par (date, ticker) -> le dernier run du jour fait foi."""
    if not PORTFOLIO_EUR_CLOSES and not CONSEQ_HIST_OBS:
        print("  [Historique] aucun close a stocker.")
        return
    if not GOOGLE_OK:
        print("  [Historique] modules Google manquants.")
        return
    try:
        svc = build("sheets", "v4", credentials=_get_creds()).spreadsheets()
        meta = svc.get(spreadsheetId=SHEET_ID).execute()
        tabs = [sh["properties"]["title"] for sh in meta["sheets"]]
        if HIST_TAB not in tabs:
            svc.batchUpdate(spreadsheetId=SHEET_ID, body={
                "requests": [{"addSheet": {"properties": {"title": HIST_TAB}}}]}).execute()
            print(f"  Onglet '{HIST_TAB}' cree")
        res = svc.values().get(spreadsheetId=SHEET_ID, range=f"{HIST_TAB}!A:C").execute()
        vals = res.get("values", []) or []
        start = 1 if (vals and vals[0] and str(vals[0][0]).strip().lower().startswith("date")) else 0
        data = {}
        for r in vals[start:]:
            if len(r) >= 3 and r[0] and r[1]:
                data[(r[0], r[1])] = r[2]
        today = datetime.date.today().isoformat()
        for tk, close in PORTFOLIO_EUR_CLOSES.items():
            data[(today, tk)] = str(close)
        # VL Conseq datées (CZK) par date publiée -> upsert (idempotent)
        for tk, obs in (CONSEQ_HIST_OBS or {}).items():
            dd, nav = obs
            if dd and nav:
                data[(dd, tk)] = str(nav)
        out = [["Date", "Ticker", "Close_EUR"]]
        for key in sorted(data.keys()):
            out.append([key[0], key[1], data[key]])
        svc.values().clear(spreadsheetId=SHEET_ID, range=f"{HIST_TAB}!A:C").execute()
        svc.values().update(spreadsheetId=SHEET_ID, range=f"{HIST_TAB}!A1",
                            valueInputOption="RAW", body={"values": out}).execute()
        print(f"  Historique_Prix : {len(PORTFOLIO_EUR_CLOSES)} close du {today} "
              f"+ {len(CONSEQ_HIST_OBS)} VL Conseq datees ({len(out)-1} lignes au total)")
    except Exception as e:
        print(f"  [Historique] erreur : {e}")


if __name__ == "__main__":
    print("=" * 55)
    print("  Mise à jour prix + variations → Google Sheets")
    print("=" * 55)
    rows = collecter_prix()
    ok   = ecrire_google_sheets(rows)
    if ok:
        print("\n✅ Prix et variations écrits")
    else:
        print("\n⚠️  Vérifier service_account.json")
    try:
        append_price_history()
    except Exception as e:
        print(f"  [Historique] {e}")
    print("=" * 55)
