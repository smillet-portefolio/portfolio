Prépare le résumé des actualités des actions et cryptos détenues par Sébastien (et ses enfants) et publie-le dans l'onglet « News » de son Google Sheet, lu par l'onglet 📰 Infos de son dashboard financier. Tout le texte produit doit être en FRANÇAIS. Travaille de façon autonome, sans poser de question.

1. Liste des titres suivis : exécute
   python update_news_gsheet.py --holdings
   Il renvoie un JSON [{name, ticker, isin, kind ("action" ou "crypto"), owner}] lu en lecture seule depuis le Google Sheet. Suis exactement ces titres (pas d'ETF). Exécute aussi `date` (fuseau Europe/Prague) pour connaître la date et l'heure.

2. Pour CHAQUE titre, cherche avec WebSearch les actualités publiées dans les DERNIÈRES 48 HEURES uniquement (vérifie la date de chaque article ; ignore tout ce qui est plus ancien). Sources : presse économique française (Les Échos, Boursorama, Zonebourse, BFM Bourse, ABC Bourse, Investir, Le Revenu, AOF…) ET internationale (Reuters, Bloomberg, Financial Times, WSJ, CNBC, MarketWatch, Handelsblatt ; CoinDesk / The Block pour les cryptos). Privilégie les articles de presse aux notes boursières générées automatiquement. Fais des recherches en français et en anglais.
   Retiens pour chaque titre 0 à 4 faits marquants : résultats, prévisions, contrats, acquisitions, recommandations / objectifs d'analystes, mouvements de cours notables (avec leur raison), réglementation, litiges, dirigeants. Pour Bitcoin et Ethereum : prix et variation, flux ETF, régulation, événements de marché.
   Méthode OBLIGATOIRE pour ne rien manquer — pour CHAQUE titre, fais AU MINIMUM ces 3 recherches séparées :
     a) en anglais avec le nom ET le ticker : "<nom> <ticker> stock news <date du jour>" (ex. "Vistra VST stock news October 21 2026") ;
     b) en anglais : "<nom> price target analyst" (relèvements / abaissements d'objectifs, changements de recommandation) ;
     c) en français : "<nom> action bourse actualité" (ou en allemand pour les valeurs allemandes / autrichiennes : "<nom> Aktie").
   Si un titre a varié de plus de ±3 % sur la séance, cherche spécifiquement la raison ("why <nom> stock up/down today") et indique-la.
   Ne conclus à "aucune info" qu'après ces 3 recherches.
   Si aucune info dans les 48 h : "items": [] — n'invente rien, ne reprends pas d'anciennes infos.

3. Écris avec l'outil Write le fichier news_portefeuille.json (UTF-8, dans le dossier courant) :
{
 "generated_at": "<date-heure ISO de Prague, ex. 2026-10-21T07:05+02:00>",
 "summary": "<2-3 phrases : les faits les plus importants pour le portefeuille>",
 "stocks": [ {"name": "...", "ticker": "...", "kind": "action|crypto", "owner": [...repris de l'étape 1...],
              "items": [ {"sentiment": "pos|neg|neu", "text": "<1-2 phrases, chiffres précis>", "source": "<média>", "url": "<lien de l'article>", "date": "JJ/MM"} ] } ],
 "agenda": [ {"date": "JJ/MM", "text": "<titre> — <publication à venir dans les 15 prochains jours>"} ]
}
   Un objet par titre de l'étape 1, dans le même ordre, y compris ceux sans info (items vide).

4. Publie : python update_news_gsheet.py --write news_portefeuille.json
   Le script n'écrit QUE dans l'onglet « News ». Ne modifie aucun autre fichier.

5. Termine par un court compte rendu : nombre de titres avec actualité, les 3 faits principaux. Synthèse indicative, pas un conseil en investissement.
