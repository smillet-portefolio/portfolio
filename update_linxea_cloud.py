#!/usr/bin/env python3
"""
update_linxea_cloud.py — Runner CLOUD pour la mise à jour Linxea via OneDrive
----------------------------------------------------------------------------
Conçu pour GitHub Actions (aucun PC allumé requis) :
  1. obtient un access_token OneDrive à partir du refresh_token (compte perso),
  2. télécharge linxea.xlsx depuis OneDrive (Microsoft Graph),
  3. met à jour les prix (logique de update_linxea_prix_v11.py),
  4. ré-upload le fichier dans OneDrive,
  5. (optionnel) met à jour le secret MS_REFRESH_TOKEN si Microsoft l'a renouvelé.

Variables d'environnement :
  MS_CLIENT_ID      (secret)  — Application (client) ID Azure
  MS_REFRESH_TOKEN  (secret)  — obtenu via onedrive_auth.py
  ONEDRIVE_PATH     (option)  — défaut "Documents/banque/bourse/linxea.xlsx"
  MS_TENANT         (option)  — défaut "consumers" (compte personnel)
  GH_PAT, GH_REPO   (option)  — pour auto-renouveler le secret refresh token

Prérequis : pip install requests yfinance openpyxl pynacl
"""
import os
import sys
import base64
import tempfile
import requests

import update_linxea_prix_v11 as lx   # réutilise taux_cnb / prix_binance / mise_a_jour_linxea

TENANT        = os.environ.get("MS_TENANT", "consumers")
CLIENT_ID     = os.environ.get("MS_CLIENT_ID")
REFRESH_TOKEN = os.environ.get("MS_REFRESH_TOKEN")
ONEDRIVE_PATH = os.environ.get("ONEDRIVE_PATH", "Documents/banque/bourse/linxea.xlsx")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def get_tokens():
    if not CLIENT_ID or not REFRESH_TOKEN:
        print("ERREUR : MS_CLIENT_ID et MS_REFRESH_TOKEN requis (secrets GitHub).")
        sys.exit(1)
    r = requests.post(
        f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token",
        data={"grant_type": "refresh_token", "client_id": CLIENT_ID,
              "refresh_token": REFRESH_TOKEN,
              "scope": "Files.ReadWrite offline_access"}, timeout=30)
    j = r.json()
    if "access_token" not in j:
        print("ERREUR auth OneDrive :", j)
        print("Le refresh token a peut-être expiré (>90 j) — relance onedrive_auth.py.")
        sys.exit(1)
    return j["access_token"], j.get("refresh_token")


def update_github_secret(name, value):
    """Renouvelle un secret GitHub (nécessite GH_PAT avec droit secrets:write)."""
    pat  = os.environ.get("GH_PAT")
    repo = os.environ.get("GH_REPO")
    if not pat or not repo:
        return False
    try:
        from nacl import encoding, public
    except Exception:
        print("pynacl absent — secret non renouvelé.")
        return False
    h = {"Authorization": "Bearer " + pat, "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    k = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
                     headers=h, timeout=30).json()
    pk  = public.PublicKey(k["key"].encode(), encoding.Base64Encoder())
    enc = base64.b64encode(public.SealedBox(pk).encrypt(value.encode())).decode()
    r = requests.put(f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
                     headers=h, json={"encrypted_value": enc, "key_id": k["key_id"]}, timeout=30)
    ok = r.status_code in (201, 204)
    print(("Secret " + name + " renouvelé.") if ok else ("Renouvellement secret KO " + str(r.status_code)))
    return ok


def main():
    print("=" * 55)
    print("  Linxea CLOUD — mise à jour via OneDrive (Graph)")
    print("=" * 55)

    token, new_rt = get_tokens()
    H = {"Authorization": "Bearer " + token}
    base = "https://graph.microsoft.com/v1.0/me/drive/root:/" + ONEDRIVE_PATH + ":"

    # 1) Téléchargement
    r = requests.get(base + "/content", headers=H, timeout=90)
    if r.status_code != 200:
        print("ERREUR téléchargement OneDrive :", r.status_code, r.text[:300]); sys.exit(1)
    tmp = os.path.join(tempfile.gettempdir(), "linxea.xlsx")
    with open(tmp, "wb") as f:
        f.write(r.content)
    print(f"OK téléchargé {len(r.content)} octets -> {tmp}")

    # 2) Mise à jour des prix (uniquement linxea.xlsx)
    cnb = lx.taux_cnb()
    btc = lx.prix_binance("BTCEUR")
    eth = lx.prix_binance("ETHEUR")
    if not lx.mise_a_jour_linxea(tmp, btc, eth, cnb):
        print("ERREUR : mise à jour des prix échouée."); sys.exit(1)

    # 3) Ré-upload (simple upload, fichier < 4 Mo)
    with open(tmp, "rb") as f:
        data = f.read()
    r = requests.put(base + "/content",
                     headers={**H, "Content-Type": XLSX_MIME}, data=data, timeout=180)
    if r.status_code not in (200, 201):
        print("ERREUR upload OneDrive :", r.status_code, r.text[:300]); sys.exit(1)
    print(f"OK ré-uploadé sur OneDrive ({len(data)} octets).")

    # 4) Renouvellement éventuel du refresh token
    if new_rt and new_rt != REFRESH_TOKEN:
        if not update_github_secret("MS_REFRESH_TOKEN", new_rt):
            print("NOTE : refresh token renouvelé par Microsoft mais non persisté "
                  "(pas de GH_PAT). Si l'auth échoue plus tard, relance onedrive_auth.py.")

    print("\nTerminé.")


if __name__ == "__main__":
    main()
