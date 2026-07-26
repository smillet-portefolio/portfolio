#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_price_history_gsheet.py — Backfill UNIQUE de l'historique des cours
============================================================================
A lancer UNE SEULE FOIS. Recupere l'historique quotidien Yahoo de chaque
action / ETF detenu, DEPUIS SA PREMIERE DATE D'ACHAT, le convertit en EUR
(taux de change quotidiens) et l'ecrit dans l'onglet "Historique_Prix" du
Google Sheet, au format long : Date | Ticker | Close_EUR.

Ensuite, la mise a jour quotidienne (update_prix_gsheet.py) ajoute
automatiquement le close du jour a ce meme onglet — plus besoin de relancer
ce backfill.

Le dashboard lit cet onglet pour tracer l'evolution du P&L par titre.

Prerequis : pip install yfinance pandas google-auth google-api-python-client
            + service_account.json a cote (ou secret GOOGLE_SERVICE_ACCOUNT).
"""
import re
import sys
import datetime

import pandas as pd
import yfinance as yf

# Reutilise toute la config / les helpers du script de prix existant
import update_prix_gsheet as up
from googleapiclient.discovery import build

CRYPTO_BROKERS = {"ledger", "binance"}
# Crypto suivis (prix quotidien disponible via Binance/Yahoo). Les positions
# du dashboard utilisent le ticker "BTC/EUR" / "ETH/EUR" (identique a l'onglet
# Prices) ; on accepte aussi "BTC" / "ETH" par securite.
CRYPTO_TICKS   = {"BTC", "ETH", "BTC/EUR", "ETH/EUR"}
DEFAULT_START  = "2015-01-01"   # borne basse si une ligne n'a pas de date d'achat


# ── 1. Portefeuille : ticker -> {first_date, currency, name} ──────────────────
def portefeuille_info():
    holds = up.lire_holdings_sheet()
    if not holds:
        print("❌ Portefeuille indisponible (onglet Data / book2_all_rows).")
        sys.exit(1)
    info = {}
    for r in holds:
        if not isinstance(r, dict):
            continue
        tk = (r.get("ticker") or "").strip()
        if not tk or tk.upper() in up.SKIP_TICKS:
            continue
        br = (r.get("broker") or "").strip().lower()
        ty = (r.get("typeInv") or "").strip().lower()
        is_crypto = (br in CRYPTO_BROKERS or "crypto" in ty)
        if is_crypto:
            # Ne garder que le crypto suivi (BTC / ETH). Leur ticker (BTC/EUR...)
            # figure dans STATIC_TICKS mais on l'inclut volontairement ici.
            if tk not in CRYPTO_TICKS:
                continue
        else:
            if tk in up.STATIC_TICKS:      # paires FX (EUR/CZK...) : pas d'historique
                continue
            if re.search(r"structur|épargn|epargn|livret|obligation", ty):
                continue
        d   = (str(r.get("date") or r.get("dateAchat") or "")).strip()[:10]
        cur = (r.get("currency") or "EUR").strip()
        nm  = r.get("name") or tk
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            d = DEFAULT_START
        if tk not in info:
            info[tk] = {"first": d, "cur": cur, "name": nm}
        elif d < info[tk]["first"]:
            info[tk]["first"] = d
    return info


# ── 2. Historiques de change (USD, GBP -> EUR) ────────────────────────────────
def fx_series(sym):
    """Retourne {YYYY-MM-DD: close} pour une paire Yahoo (ex. EURUSD=X)."""
    try:
        h = yf.Ticker(sym).history(start="2014-01-01", interval="1d", auto_adjust=False)
        out = {}
        for idx, v in h["Close"].items():
            if v == v and v > 0:  # non-NaN
                out[idx.strftime("%Y-%m-%d")] = float(v)
        return out
    except Exception as e:
        print(f"  [FX {sym}] {e}")
        return {}


def _nearest(series, dstr):
    """Taux du jour, sinon dernier taux anterieur disponible."""
    if not series:
        return None
    if dstr in series:
        return series[dstr]
    prev = [d for d in series if d <= dstr]
    return series[max(prev)] if prev else None


def to_eur(close, cur, dstr, eurusd, eurgbp):
    cur = (cur or "EUR").strip()
    if cur in ("", "EUR"):
        return close
    if cur == "USD":
        r = _nearest(eurusd, dstr)      # USD par EUR
        return close / r if r else None
    if cur == "GBP":
        r = _nearest(eurgbp, dstr)
        return close / r if r else None
    if cur in ("GBp", "GBX"):           # pence
        r = _nearest(eurgbp, dstr)
        return (close / 100.0) / r if r else None
    return None                          # devise non geree -> ignoree


# ── 3. Symbole Yahoo pour un ticker du portefeuille ───────────────────────────
CRYPTO_YAHOO = {"BTC": "BTC-EUR", "ETH": "ETH-EUR",
                "BTC/EUR": "BTC-EUR", "ETH/EUR": "ETH-EUR"}
def yahoo_symbol(tick, cur_hint):
    if tick in CRYPTO_YAHOO:
        return CRYPTO_YAHOO[tick]
    ov = up.YS_OVERRIDE.get(tick)
    if ov:
        return ov
    if any(c in tick for c in (".", "-", "=")):
        return tick
    sym, prix, _ = up.resolve_yahoo(tick)   # essaie .DE/.MI/.PA/... (1 requete)
    return sym


# ── 4. Main ───────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Backfill historique des cours -> onglet Historique_Prix")
    print("=" * 60)

    info = portefeuille_info()
    print(f"\n{len(info)} titres a traiter.")

    print("\nTelechargement des taux de change quotidiens...")
    eurusd = fx_series("EURUSD=X")
    eurgbp = fx_series("EURGBP=X")
    print(f"  EURUSD : {len(eurusd)} jours   |   EURGBP : {len(eurgbp)} jours")

    rows = []   # [date, ticker, close_eur]
    for tk, meta in sorted(info.items()):
        sym = yahoo_symbol(tk, meta["cur"])
        try:
            t = yf.Ticker(sym)
            cur = None
            try:
                cur = t.fast_info.currency
            except Exception:
                cur = None
            cur = cur or meta["cur"]
            h = t.history(start=meta["first"], interval="1d", auto_adjust=False)
            n = 0
            for idx, close in h["Close"].items():
                if close != close or close <= 0:
                    continue
                dstr = idx.strftime("%Y-%m-%d")
                e = to_eur(float(close), cur, dstr, eurusd, eurgbp)
                if e and e > 0:
                    rows.append([dstr, tk, round(e, 4)])
                    n += 1
            print(f"  OK  {tk:<10s} ({sym}, {cur}) depuis {meta['first']} : {n} points")
        except Exception as ex:
            print(f"  KO  {tk:<10s} ({sym}) : {ex}")

    if not rows:
        print("\n❌ Aucune donnee recuperee.")
        sys.exit(1)

    # Dedoublonnage (date, ticker) -> derniere valeur, puis tri
    dedup = {(d, tk): v for d, tk, v in rows}
    out = [["Date", "Ticker", "Close_EUR"]]
    for key in sorted(dedup.keys()):
        out.append([key[0], key[1], str(dedup[key])])

    print(f"\nEcriture de {len(out)-1} lignes dans '{up.HIST_TAB}'...")
    svc = build("sheets", "v4", credentials=up._get_creds()).spreadsheets()
    metaS = svc.get(spreadsheetId=up.SHEET_ID).execute()
    tabs = [sh["properties"]["title"] for sh in metaS["sheets"]]
    if up.HIST_TAB not in tabs:
        svc.batchUpdate(spreadsheetId=up.SHEET_ID, body={
            "requests": [{"addSheet": {"properties": {"title": up.HIST_TAB}}}]}).execute()
        print(f"  Onglet '{up.HIST_TAB}' cree")
    svc.values().clear(spreadsheetId=up.SHEET_ID, range=f"{up.HIST_TAB}!A:C").execute()
    svc.values().update(spreadsheetId=up.SHEET_ID, range=f"{up.HIST_TAB}!A1",
                        valueInputOption="RAW", body={"values": out}).execute()
    print(f"\n✅ Backfill termine : {len(out)-1} lignes ecrites dans '{up.HIST_TAB}'.")
    print("   La mise a jour quotidienne ajoutera desormais le close du jour.")


if __name__ == "__main__":
    main()
