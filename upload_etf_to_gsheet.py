#!/usr/bin/env python3
"""
upload_etf_to_gsheet.py
Lit repartition_ETFs.xlsx et écrit 3 onglets dans Google Sheets :
  ETF_Country  : répartition géographique (% par pays, par ETF)
  ETF_Sector   : répartition sectorielle  (% par secteur, par ETF)
  ETF_Top10    : top 10 positions          (% par position, par ETF)

Prérequis :
    pip install pandas openpyxl google-auth google-api-python-client
"""

import os
import math
import pandas as pd

# ── CONFIG ────────────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
SHEET_ID  = "15w4s6chCytFKmPSpGXeYQ9fiJEVD_T5U9671Q0chn_Q"
# Chemins relatifs au script -> marche en LOCAL (script a cote du xlsx) ET sur
# GitHub Actions (fichiers a la racine du repo).
SERVICE_ACCOUNT_FILE = os.environ.get("SERVICE_ACCOUNT_FILE", os.path.join(HERE, "service_account.json"))
XLSX_FILE = os.environ.get("ETF_XLSX", os.path.join(HERE, "repartition_ETFs.xlsx"))
# ─────────────────────────────────────────────────────────────────────────────

def get_service():
    import json
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    sa_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if sa_env:                                  # GitHub Actions : secret en variable d'env
        creds = service_account.Credentials.from_service_account_info(json.loads(sa_env), scopes=SCOPES)
    else:                                       # local : fichier service_account.json
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds).spreadsheets()

def ensure_tab(svc, title):
    meta = svc.get(spreadsheetId=SHEET_ID).execute()
    tabs = [s["properties"]["title"] for s in meta["sheets"]]
    if title not in tabs:
        svc.batchUpdate(spreadsheetId=SHEET_ID, body={
            "requests": [{"addSheet": {"properties": {"title": title}}}]
        }).execute()
        print(f"  + onglet '{title}' créé")

def write_tab(svc, tab, values):
    svc.values().clear(spreadsheetId=SHEET_ID, range=f"{tab}!A:ZZ").execute()
    svc.values().update(
        spreadsheetId=SHEET_ID,
        range=f"{tab}!A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()
    print(f"  ✅ {tab} : {len(values)} lignes écrites")

def clean(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        # Toujours écrire avec point décimal (pas virgule)
        return str(round(v, 6)).replace(",", ".")
    return v

def df_to_values(df):
    rows = [list(df.columns)]
    for _, row in df.iterrows():
        rows.append([clean(v) for v in row])
    return rows

def main():
    try:
        from google.oauth2 import service_account
    except ImportError:
        print("❌ pip install google-auth google-api-python-client")
        return

    print(f"Lecture : {XLSX_FILE}")

    # by country – garder seulement les lignes ETF (ticker valide)
    df_country = pd.read_excel(XLSX_FILE, sheet_name="by country")
    df_country = df_country[
        df_country["ticker"].notna() &
        df_country["ticker"].astype(str).str.match(r'^[A-Z0-9.]+$')
    ].fillna("")

    # by sector
    df_sector = pd.read_excel(XLSX_FILE, sheet_name="by sector")
    df_sector = df_sector[
        df_sector["ticker"].notna() &
        df_sector["ticker"].astype(str).str.match(r'^[A-Z0-9.]+$')
    ].fillna("")

    # TOP 10 positions – première colonne = nom de la position
    df_top10 = pd.read_excel(XLSX_FILE, sheet_name="TOP 10 position")
    df_top10 = df_top10.rename(columns={"Unnamed: 0": "position"}).fillna("")

    print("\nConnexion Google Sheets…")
    svc = get_service()

    for tab in ["ETF_Country", "ETF_Sector", "ETF_Top10"]:
        ensure_tab(svc, tab)

    write_tab(svc, "ETF_Country", df_to_values(df_country))
    write_tab(svc, "ETF_Sector",  df_to_values(df_sector))
    write_tab(svc, "ETF_Top10",   df_to_values(df_top10))

    print("\n✅ Données ETF uploadées dans Google Sheets")

if __name__ == "__main__":
    main()
