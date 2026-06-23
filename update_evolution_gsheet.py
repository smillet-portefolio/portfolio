#!/usr/bin/env python3
"""
update_evolution_gsheet.py
==========================
Calcule CÔTÉ SERVEUR (sans navigateur) la ligne d'évolution quotidienne du
portefeuille — exactement comme la fonction JS `getTodayEvoRow()` du dashboard —
et l'écrit dans Google Sheets (clé `evo_history` de l'onglet "Data").

Logique répliquée fidèlement depuis dashboard_portefeuille.html :
  - getTodayEvoRow()  (lignes ~4562-4630)
  - toEur()           (lignes ~3156-3165)
  - echCapEur()/obFx()(lignes ~5885-5898)
  - regroupement normBroker, investedByBroker (dépôts nets EUR),
    pfByBroker (BOOK2 qty×prix EUR + cash + obligations capital restant).

Sources de données :
  - Onglet "Prices" (écrit par update_prix_gsheet.py) -> CURRENT_PRICES
  - Onglet "Data"   (écrit par gsSaveAll côté dashboard) -> book2_all_rows,
    cash_data, oblig_data, portfolio_fx, evo_history.

Auth identique à update_prix_gsheet.py.
Variables d'environnement :
  - GOOGLE_SERVICE_ACCOUNT : JSON du compte de service (exécution cloud)
  - SHEET_ID               : ID du classeur (défaut ci-dessous)
  - DRY_RUN=1              : calcule et imprime SANS écrire

Prérequis : pip install google-auth google-api-python-client
"""

import os
import json
import datetime

# ──────────────────────────────────────────────────────────────────────────────
# Configuration (identique au script des prix)
# ──────────────────────────────────────────────────────────────────────────────
SERVICE_ACCOUNT_FILE = r"C:\Users\smill\OneDrive\Documents\banque\bourse\service_account.json"
SHEET_ID = os.environ.get("SHEET_ID", "15w4s6chCytFKmPSpGXeYQ9fiJEVD_T5U9671Q0chn_Q")
DATA_TAB = "Data"
PRICES_TAB = "Prices"
DRY_RUN = os.environ.get("DRY_RUN", "") in ("1", "true", "True", "yes")
# Mode gel : run du soir (18:00) -> met a jour la ligne du jour ET la gele.
FREEZE = (os.environ.get("EVO_FREEZE", "") in ("1", "true", "True", "yes")
          or os.environ.get("RUN_MODE", "").lower() == "evening")
CHUNK = 45000  # même limite de découpe que gsSaveAll côté dashboard

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_OK = True
except ImportError:
    print("pip install google-auth google-api-python-client")
    GOOGLE_OK = False


# ══════════════════════════════════════════════════════════════════════════════
# CASH_BASE_DEPOSITS — copié intégralement depuis le dashboard (var line ~6446).
# Dépôts/retraits "de base" (historique) combinés avec CASH_DATA.deposits pour
# calculer l'investi net par broker. amountEur prioritaire si présent.
# ══════════════════════════════════════════════════════════════════════════════
CASH_BASE_DEPOSITS = [
    {"date": "2025-05-30", "broker": "TRADING 212", "amount": 2406.74, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-05-12", "broker": "SAXO", "amount": 15000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-05-08", "broker": "IBKR", "amount": 15000.0, "currency": "EUR", "type": "retrait"},
    {"date": "2026-05-07", "broker": "KB", "amount": 7419.79, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-05-30", "broker": "TRADING 212", "amount": 601.68, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-05-06", "broker": "KB", "amount": 35304.07, "currency": "EUR", "type": "retrait"},
    {"date": "2026-05-06", "broker": "IBKR", "amount": 35274.82, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-05-30", "broker": "TRADING 212", "amount": 561.57, "currency": "EUR", "type": "retrait"},
    {"date": "2025-06-02", "broker": "TRADING 212", "amount": 2997.59, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-04-13", "broker": "XTB", "amount": 2000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-04-10", "broker": "KB", "amount": 24628.28, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-04-10", "broker": "IBKR", "amount": 15100.0, "currency": "EUR", "type": "retrait"},
    {"date": "2026-04-09", "broker": "IBKR", "amount": 17829.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-04-09", "broker": "SAXO", "amount": 19015.42, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-06", "broker": "TRADING 212", "amount": 20202.02, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-06", "broker": "TRADING 212", "amount": 2626.26, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-03-07", "broker": "IBKR", "amount": 7564.0, "currency": "EUR", "type": "retrait"},
    {"date": "2026-03-06", "broker": "IBKR", "amount": 7565.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-02-10", "broker": "SAXO", "amount": 2267.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-02-06", "broker": "IBKR", "amount": 4492.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-02-06", "broker": "IBKR", "amount": 500.0, "currency": "EUR", "type": "retrait"},
    {"date": "2026-01-19", "broker": "IBKR", "amount": 1500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-01-16", "broker": "SAXO", "amount": 3000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-01-12", "broker": "SAXO", "amount": 2650.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-06", "broker": "TRADING 212", "amount": 2626.57, "currency": "EUR", "type": "retrait"},
    {"date": "2026-01-06", "broker": "IBKR", "amount": 6181.48, "currency": "EUR", "type": "retrait"},
    {"date": "2026-01-03", "broker": "IBKR", "amount": 6199.63, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-09", "broker": "TRADING 212", "amount": 4033.07, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-12-13", "broker": "IBKR", "amount": 2348.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-12-05", "broker": "IBKR", "amount": 1448.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-12-05", "broker": "IBKR", "amount": 1445.0, "currency": "EUR", "type": "retrait"},
    {"date": "2025-12-02", "broker": "SAXO", "amount": 4550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-12-01", "broker": "XTB", "amount": 4550.0, "currency": "EUR", "type": "retrait"},
    {"date": "2025-06-09", "broker": "TRADING 212", "amount": 4033.07, "currency": "EUR", "type": "retrait"},
    {"date": "2025-11-07", "broker": "IBKR", "amount": 2460.0, "currency": "EUR", "type": "retrait"},
    {"date": "2025-11-06", "broker": "IBKR", "amount": 2463.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-14", "broker": "TRADING 212", "amount": 9863.12, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-14", "broker": "TRADING 212", "amount": 9543.89, "currency": "EUR", "type": "retrait"},
    {"date": "2025-10-15", "broker": "SAXO", "amount": 9400.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-10-07", "broker": "KB", "amount": 13709.77, "currency": "EUR", "type": "retrait"},
    {"date": "2025-10-07", "broker": "IBKR", "amount": 4319.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-14", "broker": "TRADING 212", "amount": 603.86, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-16", "broker": "TRADING 212", "amount": 685.9, "currency": "EUR", "type": "retrait"},
    {"date": "2025-09-09", "broker": "XTB", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-09-04", "broker": "IBKR", "amount": 10070.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-09-04", "broker": "IBKR", "amount": 10000.0, "currency": "EUR", "type": "retrait"},
    {"date": "2025-06-16", "broker": "TRADING 212", "amount": 645.51, "currency": "EUR", "type": "retrait"},
    {"date": "2025-08-07", "broker": "IBKR", "amount": 4500.0, "currency": "EUR", "type": "retrait"},
    {"date": "2025-08-06", "broker": "IBKR", "amount": 8140.8, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-16", "broker": "TRADING 212", "amount": 403.47, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-07-28", "broker": "IBKR", "amount": 600.0, "currency": "EUR", "type": "retrait"},
    {"date": "2025-07-26", "broker": "IBKR", "amount": 569.7, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-07-16", "broker": "IBKR", "amount": 1600.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-07-15", "broker": "IBKR", "amount": 2026.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-23", "broker": "TRADING 212", "amount": 120.65, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-07-09", "broker": "IBKR", "amount": 9000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-23", "broker": "TRADING 212", "amount": 120.65, "currency": "EUR", "type": "retrait"},
    {"date": "2025-07-04", "broker": "IBKR", "amount": 4052.91, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-30", "broker": "TRADING 212", "amount": 22.18, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-07-07", "broker": "TRADING 212", "amount": 9001.83, "currency": "EUR", "type": "retrait"},
    {"date": "2025-07-14", "broker": "TRADING 212", "amount": 2610.52, "currency": "EUR", "type": "retrait"},
    {"date": "2025-06-17", "broker": "XTB", "amount": 900.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-16", "broker": "KB", "amount": 9506.77, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-07-31", "broker": "TRADING 212", "amount": 54.23, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-08-31", "broker": "TRADING 212", "amount": 129.02, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-09-30", "broker": "TRADING 212", "amount": 38.17, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-14", "broker": "KB", "amount": 10466.99, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-10-07", "broker": "TRADING 212", "amount": 1244.2, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-10-31", "broker": "TRADING 212", "amount": 44.3, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-11-06", "broker": "TRADING 212", "amount": 2226.3, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-06-10", "broker": "XTB", "amount": 4000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-11-27", "broker": "TRADING 212", "amount": 3522.58, "currency": "EUR", "type": "retrait"},
    {"date": "2025-12-17", "broker": "TRADING 212", "amount": 1123.62, "currency": "EUR", "type": "retrait"},
    {"date": "2026-01-12", "broker": "TRADING 212", "amount": 2650.0, "currency": "EUR", "type": "retrait"},
    {"date": "2026-03-30", "broker": "TRADING 212", "amount": 122.22, "currency": "EUR", "type": "retrait"},
    {"date": "2026-04-09", "broker": "TRADING 212", "amount": 13967.9, "currency": "EUR", "type": "dépôt"},
    {"date": "2026-04-26", "broker": "TRADING 212", "amount": 2119.92, "currency": "EUR", "type": "retrait"},
    {"date": "2026-05-04", "broker": "TRADING 212", "amount": 650.0, "currency": "EUR", "type": "retrait"},
    {"date": "2026-05-07", "broker": "TRADING 212", "amount": 2698.36, "currency": "EUR", "type": "retrait"},
    {"date": "2025-11-30", "broker": "TRADING 212", "amount": 9.82, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-05-28", "broker": "XTB", "amount": 3000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-05-27", "broker": "XTB", "amount": 7000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2025-05-07", "broker": "KB", "amount": 42117.93, "currency": "EUR", "type": "dépôt"},
    {"date": "2023-10-13", "broker": "LINXEA", "amount": 61500.0, "currency": "EUR", "type": "retrait"},
    {"date": "2023-03-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2023-02-13", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2023-01-13", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-12-14", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-11-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-10-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-09-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-08-15", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-07-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-06-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-05-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-04-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-03-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-02-10", "broker": "LINXEA", "amount": 1000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2022-01-10", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-12-10", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-11-10", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-10-10", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-09-10", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-08-10", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-07-10", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-06-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-05-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-04-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-03-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-02-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2021-01-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-12-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-11-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-10-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-09-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-08-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-07-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-06-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-05-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-04-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-03-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-02-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2020-01-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-12-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-11-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-10-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-09-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-08-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-07-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-06-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-05-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-04-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-03-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-02-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2019-01-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-12-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-12-03", "broker": "LINXEA", "amount": 10000.0, "currency": "EUR", "type": "retrait"},
    {"date": "2018-11-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-10-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-09-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-08-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-07-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-06-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-05-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-04-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-03-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-02-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2018-01-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-12-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-11-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-10-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-09-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-08-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-07-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-06-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-05-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-04-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-03-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-02-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2017-01-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-12-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-11-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-10-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-09-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-08-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-07-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-06-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-05-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-04-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-03-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-02-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2016-01-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-12-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-11-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-10-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-09-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-08-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-07-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-06-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-05-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-04-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-03-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-02-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2015-01-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-12-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-11-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-10-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-09-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-08-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-07-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-06-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-05-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-04-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-03-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-02-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2014-01-15", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-12-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-11-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-10-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-09-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-08-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-07-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-06-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-05-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-04-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-03-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-02-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2013-01-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2012-12-10", "broker": "LINXEA", "amount": 300.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2011-02-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2011-01-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-12-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-11-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-10-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-09-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-08-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-07-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-06-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-05-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-04-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-03-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-02-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2010-01-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-12-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-11-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-10-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-09-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-08-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-07-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-06-10", "broker": "LINXEA", "amount": 225.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-05-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-04-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-03-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-02-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2009-01-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-12-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-11-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-10-10", "broker": "LINXEA", "amount": 550.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-09-10", "broker": "LINXEA", "amount": 200.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-08-10", "broker": "LINXEA", "amount": 200.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-07-10", "broker": "LINXEA", "amount": 200.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-06-10", "broker": "LINXEA", "amount": 200.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-05-10", "broker": "LINXEA", "amount": 200.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-04-10", "broker": "LINXEA", "amount": 200.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-03-10", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-02-10", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2008-01-10", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-12-10", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-11-14", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-10-15", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-09-13", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-08-15", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-07-13", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-06-19", "broker": "LINXEA", "amount": 3600.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-06-13", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-05-23", "broker": "LINXEA", "amount": 2000.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-05-15", "broker": "LINXEA", "amount": 125.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-04-16", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
    {"date": "2007-03-01", "broker": "LINXEA", "amount": 500.0, "currency": "EUR", "type": "dépôt"},
]


# ══════════════════════════════════════════════════════════════════════════════
# Conversion devise -> EUR — réplique EXACTE de toEur() (dashboard ~3156).
# FX_RATES.USD/GBP/CZK représentent : 1 unité de la devise = X EUR
#   (USD: amount * FX.USD ; CZK: amount * FX.CZK où FX.CZK = 1/eurczk ~ 0.04).
# ══════════════════════════════════════════════════════════════════════════════
FX_RATES = {"USD": None, "GBP": None, "CZK": None, "CHF": None}


def to_eur(amount, currency):
    """Identique à toEur(amount, currency) du dashboard."""
    if amount is None:
        return None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None
    if amount != amount:  # NaN
        return None
    if currency == "EUR":
        return amount
    if currency == "USD":
        return amount * (FX_RATES.get("USD") or 0.893)
    if currency == "GBp":
        return amount * (FX_RATES.get("GBP") or 1.172) / 100.0  # pence -> GBP -> EUR
    if currency == "GBP":
        return amount * (FX_RATES.get("GBP") or 1.172)
    if currency == "CHF":
        return amount * (FX_RATES.get("CHF") or 1.06)
    if currency == "CZK":
        return amount * (FX_RATES.get("CZK") or (1.0 / 25.0))
    return amount  # fallback : traité comme EUR


def ob_fx(p):
    """Réplique obFx(p) : taux de change pour une obligation en devise étrangère."""
    if not p or not p.get("currency") or p.get("currency") == "EUR":
        return 1
    rate = FX_RATES.get(p.get("currency"))
    return rate if rate else (p.get("fxRate") or 1)


def ech_cap_eur(p, e):
    """Réplique echCapEur(p, e) : capital d'une échéance converti en EUR.

    - obligation EUR -> capital tel quel
    - capEur figé (verrouillé à la date passée) -> on l'utilise
    - sinon capital * obFx(p)
    """
    if not p.get("currency") or p.get("currency") == "EUR":
        return e.get("capital") or 0
    if e.get("capEur") is not None:
        return e.get("capEur")
    return (e.get("capital") or 0) * ob_fx(p)


def norm_broker(b):
    """Réplique normBroker : replie 'KB*' -> 'KB' + map ledger/binance/trading 212."""
    if b and str(b).upper().startswith("KB"):
        return "KB"
    mapping = {
        "ledger": "Ledger", "LEDGER": "Ledger",
        "binance": "Binance", "BINANCE": "Binance",
        "trading 212": "TRADING 212",
    }
    return mapping.get(b, b)


# ══════════════════════════════════════════════════════════════════════════════
# Calcul de la ligne du jour — réplique EXACTE de getTodayEvoRow().
# ══════════════════════════════════════════════════════════════════════════════
def get_today_evo_row(book2_rows, cash_data, oblig_data, current_prices):
    today = datetime.date.today().isoformat()

    # ── Investi par broker = net déposé (dépôts - retraits) ──────────────────
    all_deps = list(CASH_BASE_DEPOSITS) + list((cash_data or {}).get("deposits", []))
    invested_by_broker = {}
    for d in all_deps:
        # eur = d.amountEur ?? (currency==EUR ? amount : (toEur||amount))
        if d.get("amountEur") is not None:
            eur = d["amountEur"]
        elif d.get("currency") == "EUR":
            eur = d.get("amount")
        else:
            eur = to_eur(d.get("amount"), d.get("currency"))
            if eur is None:
                eur = d.get("amount")
        net = eur if d.get("type") == "dépôt" else -eur
        b = norm_broker(d.get("broker"))
        invested_by_broker[b] = invested_by_broker.get(b, 0) + net

    # ── Valeur actuelle par broker = qty×prix EUR + cash + obligations ───────
    pf_by_broker = {}
    for r in book2_rows:
        info = current_prices.get(r.get("ticker"))
        # costEur si présent sinon toEur(cost, currency) || 0
        if r.get("costEur") is not None:
            cost_eur = r["costEur"]
        else:
            cost_eur = to_eur(r.get("cost"), r.get("currency")) or 0
        if info and info.get("price"):
            val = to_eur(r.get("qty", 0) * info["price"],
                         info.get("currency") or r.get("currency"))
            if val is None:
                val = cost_eur
        else:
            val = cost_eur
        b = norm_broker(r.get("broker") or "—")
        pf_by_broker[b] = pf_by_broker.get(b, 0) + val

    # ── Cash par broker (EUR + USD + CZK convertis) ──────────────────────────
    for b, c in ((cash_data or {}).get("cash", {}) or {}).items():
        cash_eur = (c.get("EUR") or 0) \
            + to_eur(c.get("USD") or 0, "USD") \
            + to_eur(c.get("CZK") or 0, "CZK")
        bn = norm_broker(b)
        pf_by_broker[bn] = pf_by_broker.get(bn, 0) + cash_eur

    # ── Obligations : capital restant = montant - capital reçu à ce jour ─────
    for p in (oblig_data or []):
        recu_cap = sum(
            ech_cap_eur(p, e)
            for e in (p.get("echeancier") or [])
            if e.get("date") and e["date"] <= today
        )
        cap = (p.get("montant") or 0) - recu_cap
        b = norm_broker(p.get("plateforme") or "—")
        pf_by_broker[b] = pf_by_broker.get(b, 0) + cap

    def A(b):
        return pf_by_broker.get(b, 0)

    def I(b):
        return invested_by_broker.get(b, 0)

    act_kb, act_lumo, act_lendo, act_enerfip = A("KB"), A("LUMO"), A("LENDOSPHERE"), A("ENERFIP")
    act_linxea, act_saxo, act_ibkr, act_t212 = A("LINXEA"), A("SAXO"), A("IBKR"), A("TRADING 212")
    act_jito = A("TRADING 212 JITO")
    act_xtb, act_ledger, act_binance = A("XTB"), A("Ledger"), A("Binance")
    act_bonds = act_lumo + act_lendo + act_enerfip
    act_total = sum(pf_by_broker.values())

    inv_kb, inv_lumo, inv_lendo, inv_enerfip = I("KB"), I("LUMO"), I("LENDOSPHERE"), I("ENERFIP")
    inv_linxea, inv_saxo, inv_ibkr, inv_t212 = I("LINXEA"), I("SAXO"), I("IBKR"), I("TRADING 212")
    inv_jito = I("TRADING 212 JITO")
    inv_xtb, inv_ledger, inv_binance = I("XTB"), I("Ledger"), I("Binance")
    inv_bonds = inv_lumo + inv_lendo + inv_enerfip
    inv_total = sum(invested_by_broker.values())

    return {
        "date": today,
        "act_kb": act_kb, "act_lumo": act_lumo, "act_lendo": act_lendo,
        "act_enerfip": act_enerfip, "act_bonds": act_bonds, "act_linxea": act_linxea,
        "act_saxo": act_saxo, "act_ibkr": act_ibkr, "act_t212": act_t212, "act_jito": act_jito,
        "act_xtb": act_xtb, "act_ledger": act_ledger, "act_binance": act_binance,
        "act_total": act_total,
        "act_delta": None,  # calculé après (vs dernière ligne précédente)
        "inv_kb": inv_kb, "inv_lumo": inv_lumo, "inv_lendo": inv_lendo,
        "inv_enerfip": inv_enerfip, "inv_bonds": inv_bonds, "inv_linxea": inv_linxea,
        "inv_saxo": inv_saxo, "inv_ibkr": inv_ibkr, "inv_t212": inv_t212, "inv_jito": inv_jito,
        "inv_xtb": inv_xtb, "inv_ledger": inv_ledger, "inv_binance": inv_binance,
        "inv_total": inv_total,
        "perf_total": (act_total - inv_total) / inv_total if inv_total > 0 else 0,
        "frozen": False,
        "live": True,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Auth Google (identique à update_prix_gsheet.py)
# ══════════════════════════════════════════════════════════════════════════════
def get_sheets_service():
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    sa_env = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    if sa_env:  # exécution cloud : identifiants dans une variable/secret
        creds = service_account.Credentials.from_service_account_info(
            json.loads(sa_env), scopes=SCOPES)
    else:       # exécution locale : fichier service_account.json
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service.spreadsheets()


# ══════════════════════════════════════════════════════════════════════════════
# Lecture onglet Prices -> CURRENT_PRICES + dérivation FX_RATES (paires CNB)
# ══════════════════════════════════════════════════════════════════════════════
def _parse_float(s):
    """parseFloat tolérant : gère virgule décimale et chaînes vides."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def lire_prices(sheet):
    """Lit l'onglet Prices et renvoie (current_prices, fx_from_prices)."""
    res = sheet.values().get(spreadsheetId=SHEET_ID, range=f"{PRICES_TAB}!A:L").execute()
    rows = res.get("values", [])
    current_prices = {}
    fx = {"USD": None, "GBP": None, "CZK": None}
    if len(rows) < 2:
        return current_prices, fx

    headers = [str(h).lower().strip() for h in rows[0]]

    def find_idx(pred):
        for i, h in enumerate(headers):
            if pred(h):
                return i
        return -1

    i_ticker = find_idx(lambda h: "ticker" in h)
    i_price = find_idx(lambda h: ("price" in h or "prix" in h or "close" in h))
    i_curr = find_idx(lambda h: ("curr" in h or "devise" in h))
    if i_ticker < 0 or i_price < 0:
        return current_prices, fx

    # 1) Paires CNB pour FX (comme gsLoadPrices) : EUR/CZK, USD/CZK, GBP/CZK
    eur_czk = usd_czk = gbp_czk = None
    for r in rows[1:]:
        if i_ticker >= len(r):
            continue
        t = str(r[i_ticker]).strip().upper()
        p = _parse_float(r[i_price]) if i_price < len(r) else None
        if p is None or p <= 0:
            continue
        if t == "EUR/CZK":
            eur_czk = p
        elif t == "USD/CZK":
            usd_czk = p
        elif t == "GBP/CZK":
            gbp_czk = p
    if eur_czk and usd_czk:
        fx["USD"] = usd_czk / eur_czk
    if eur_czk and gbp_czk:
        fx["GBP"] = gbp_czk / eur_czk
    if eur_czk:
        fx["CZK"] = 1.0 / eur_czk

    # 2) Prix par ticker (on exclut les paires FX, comme le dashboard)
    fx_pairs = {"EUR/CZK", "USD/CZK", "GBP/CZK", "EUR/USD", "EUR/GBP", "USD/EUR", "GBP/EUR"}
    for r in rows[1:]:
        if i_ticker >= len(r):
            continue
        t = str(r[i_ticker]).strip()
        p = _parse_float(r[i_price]) if i_price < len(r) else None
        curr = (str(r[i_curr]).strip() if (i_curr >= 0 and i_curr < len(r) and r[i_curr]) else "EUR")
        if not t or t.upper() in fx_pairs or p is None or p <= 0:
            continue
        current_prices[t] = {"price": p, "currency": curr}
    return current_prices, fx


# ══════════════════════════════════════════════════════════════════════════════
# Lecture onglet Data -> dict { clé: valeur recollée } + lignes brutes
# ══════════════════════════════════════════════════════════════════════════════
def lire_data(sheet):
    """Renvoie (data_map, raw_rows). data_map[clé] = valeur recollée (chunks)."""
    res = sheet.values().get(spreadsheetId=SHEET_ID, range=f"{DATA_TAB}!A:Z").execute()
    rows = res.get("values", [])
    data_map = {}
    for row in rows:
        if not row:
            continue
        key = row[0]
        val = "".join(str(x) for x in row[1:])  # recoller les morceaux (gsLoadAll)
        data_map[key] = val
    return data_map, rows


def chunk_value(key, value):
    """Reproduit la logique de chunking de gsSaveAll : <= CHUNK -> 1 colonne."""
    row = [key]
    if len(value) <= CHUNK:
        row.append(value)
    else:
        for i in range(0, len(value), CHUNK):
            row.append(value[i:i + CHUNK])
    return row


# ══════════════════════════════════════════════════════════════════════════════
# Programme principal
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  Mise à jour de la ligne d'évolution -> Google Sheets")
    if DRY_RUN:
        print("  *** MODE DRY_RUN : aucune écriture ***")
    print("=" * 60)

    if not GOOGLE_OK:
        print("❌ Modules Google manquants (pip install google-auth google-api-python-client)")
        return

    try:
        sheet = get_sheets_service()
    except FileNotFoundError:
        print(f"❌ Fichier service account introuvable : {SERVICE_ACCOUNT_FILE}")
        return
    except Exception as e:
        print(f"❌ Erreur d'authentification : {e}")
        return

    # 1) Prices -> prix + FX
    try:
        current_prices, fx_from_prices = lire_prices(sheet)
    except Exception as e:
        print(f"❌ Erreur lecture onglet Prices : {e}")
        return
    print(f"  Prix chargés (Prices) : {len(current_prices)} tickers")

    # 2) Data -> clés
    try:
        data_map, raw_rows = lire_data(sheet)
    except Exception as e:
        print(f"❌ Erreur lecture onglet Data : {e}")
        return

    # Robustesse : sans book2_all_rows / cash_data on ne calcule rien
    if "book2_all_rows" not in data_map or "cash_data" not in data_map:
        print("❌ L'onglet Data ne contient pas 'book2_all_rows' et/ou 'cash_data'.")
        print("   -> Sauvegardez d'abord les données depuis le dashboard (💾). "
              "Aucune écriture effectuée.")
        return

    def parse_json(key, default):
        raw = data_map.get(key)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception as e:
            print(f"  ⚠️ JSON invalide pour '{key}' : {e}")
            return default

    book2_rows = parse_json("book2_all_rows", [])
    cash_data = parse_json("cash_data", {})
    oblig_data = parse_json("oblig_data", [])
    portfolio_fx = parse_json("portfolio_fx", {})
    evo_history = parse_json("evo_history", [])
    if not isinstance(evo_history, list):
        evo_history = []

    if not isinstance(book2_rows, list) or not book2_rows:
        print("❌ book2_all_rows vide ou invalide. Aucune écriture.")
        return

    # 3) FX_RATES : on privilégie le CNB FRAIS de l'onglet Prices (exactement
    #    comme gsLoadPrices du dashboard, qui fixe FX_RATES.CZK = 1/eurCzk depuis
    #    Prices et ne restaure JAMAIS le CZK depuis portfolio_fx). On ne retombe
    #    sur portfolio_fx que si la paire CNB est absente de Prices.
    #    [corrige 23/06/2026 : avant on privilegiait portfolio_fx (taux fige au
    #     dernier 💾 Save) -> KB en CZK divergeait du dashboard]
    FX_RATES["USD"] = fx_from_prices.get("USD") or portfolio_fx.get("USD")
    FX_RATES["GBP"] = fx_from_prices.get("GBP") or portfolio_fx.get("GBP")
    FX_RATES["CZK"] = fx_from_prices.get("CZK") or portfolio_fx.get("CZK")
    # Mêmes fallbacks que le dashboard
    if not FX_RATES["USD"]:
        FX_RATES["USD"] = 0.893
    if not FX_RATES["GBP"]:
        FX_RATES["GBP"] = 1.172
    print(f"  FX_RATES : USD={FX_RATES['USD']}, GBP={FX_RATES['GBP']}, CZK={FX_RATES['CZK']} "
          f"(source: {'Prices/CNB' if fx_from_prices.get('CZK') else 'portfolio_fx'})")

    # 4) Calcul de la ligne du jour
    snap = get_today_evo_row(book2_rows, cash_data, oblig_data, current_prices)

    # act_delta = act_total du jour - act_total de la dernière ligne PRÉCÉDENTE
    today = snap["date"]
    if datetime.date.fromisoformat(today).weekday() >= 5:   # 5=samedi, 6=dimanche
        print(f"\n  Week-end ({today}) - pas de ligne Evolution (lun-ven uniquement).")
        return
    before = [r for r in evo_history if r.get("date") and r["date"] < today]
    before.sort(key=lambda r: r["date"], reverse=True)
    if before:
        snap["act_delta"] = round((snap["act_total"] - before[0].get("act_total", 0)) * 100) / 100
    else:
        snap["act_delta"] = None

    # 5) Résumé lisible
    print("\n  --- Ligne du jour (" + today + ") ---")
    print(f"  Valeur totale (act_total) : {snap['act_total']:,.2f} €")
    print(f"  Investi total (inv_total) : {snap['inv_total']:,.2f} €")
    print(f"  Performance               : {snap['perf_total']*100:,.2f} %")
    if snap["act_delta"] is not None:
        print(f"  Delta vs hier             : {snap['act_delta']:+,.2f} €")
    print("  Par broker (valeur actuelle / investi) :")
    brokers = [
        ("KB", "act_kb", "inv_kb"), ("LUMO", "act_lumo", "inv_lumo"),
        ("LENDOSPHERE", "act_lendo", "inv_lendo"), ("ENERFIP", "act_enerfip", "inv_enerfip"),
        ("LINXEA", "act_linxea", "inv_linxea"), ("SAXO", "act_saxo", "inv_saxo"),
        ("IBKR", "act_ibkr", "inv_ibkr"), ("TRADING 212", "act_t212", "inv_t212"),
        ("TRADING 212 JITO", "act_jito", "inv_jito"),
        ("XTB", "act_xtb", "inv_xtb"), ("Ledger", "act_ledger", "inv_ledger"),
        ("Binance", "act_binance", "inv_binance"),
    ]
    for label, ak, ik in brokers:
        print(f"    {label:<14s} : {snap[ak]:>12,.2f} €   /  {snap[ik]:>12,.2f} €")
    print(f"    {'(obligations)':<14s} : {snap['act_bonds']:>12,.2f} €   /  {snap['inv_bonds']:>12,.2f} €")

    # 6) Fusion dans evo_history selon le mode :
    #    - matin (live)  : cree/rafraichit la ligne du jour (frozen=False, live=True),
    #                      sans toucher une ligne deja gelee.
    #    - soir (FREEZE) : met a jour la ligne du jour avec les valeurs du jour ET la gele
    #                      (frozen=True, live=False) ; la cree si absente.
    snap["frozen"] = bool(FREEZE)
    snap["live"]   = (not FREEZE)
    print(f"\n  Mode : {'GEL (soir)' if FREEZE else 'LIVE (matin)'}")
    idx = next((i for i, r in enumerate(evo_history) if r.get("date") == today), -1)
    if FREEZE:
        if idx != -1:
            evo_history[idx] = snap
            action = "mise a jour + gelee"
        else:
            evo_history.append(snap)
            action = "creee + gelee"
    else:
        if idx != -1:
            if evo_history[idx].get("frozen"):
                print(f"\n  i  La ligne du {today} est deja gelee — aucune modification.")
                return
            evo_history[idx] = snap
            action = "rafraichie (live)"
        else:
            evo_history.append(snap)
            action = "creee (live)"

    if DRY_RUN:
        print(f"\n  [DRY_RUN] Ligne {action} en mémoire — écriture NON effectuée.")
        print(f"  [DRY_RUN] evo_history contiendrait {len(evo_history)} lignes.")
        return

    # 7) Réécriture de l'onglet Data en préservant toutes les autres clés.
    #    On reconstruit chaque ligne :
    #      - 'evo_history' -> nouvelle valeur (re-chunkée)
    #      - toute autre clé -> ligne brute d'origine inchangée
    new_evo_raw = json.dumps(evo_history, ensure_ascii=False, separators=(",", ":"))
    out_rows = []
    seen_evo = False
    for row in raw_rows:
        if not row:
            out_rows.append(row)
            continue
        key = row[0]
        if key == "evo_history":
            out_rows.append(chunk_value("evo_history", new_evo_raw))
            seen_evo = True
        else:
            out_rows.append(row)  # préservé à l'identique (y compris _saved_at)
    if not seen_evo:
        # evo_history absent jusqu'ici : on l'ajoute (avant _saved_at si possible)
        new_row = chunk_value("evo_history", new_evo_raw)
        insert_at = next((i for i, r in enumerate(out_rows) if r and r[0] == "_saved_at"), len(out_rows))
        out_rows.insert(insert_at, new_row)

    try:
        sheet.values().clear(spreadsheetId=SHEET_ID, range=f"{DATA_TAB}!A:Z").execute()
        sheet.values().update(
            spreadsheetId=SHEET_ID,
            range=f"{DATA_TAB}!A1",
            valueInputOption="RAW",
            body={"range": f"{DATA_TAB}!A1", "majorDimension": "ROWS", "values": out_rows},
        ).execute()
        print(f"\n  ✅ Ligne du {today} {action}. evo_history = {len(evo_history)} lignes écrites.")
    except Exception as e:
        print(f"\n  ❌ Erreur d'écriture : {e}")
        return

    print("=" * 60)


if __name__ == "__main__":
    main()
