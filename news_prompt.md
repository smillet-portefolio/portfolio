Prépare le résumé des actualités des actions, cryptos et marchés des ETF détenus par Sébastien (et ses enfants) et publie-le dans l'onglet « News » de son Google Sheet, lu par l'onglet 📰 Infos de son dashboard financier. Tout le texte produit doit être en FRANÇAIS. Travaille de façon autonome, sans poser de question.

1. Liste des titres suivis : exécute
   python update_news_gsheet.py --holdings
   Il renvoie un JSON [{name, ticker, isin, kind ("action" ou "crypto"), owner, var_1d_pct, var_ytd_pct}] lu en lecture seule depuis le Google Sheet (var_1d_pct = variation de la dernière séance en %). Suis exactement ces titres (pas d'ETF). Exécute aussi `date` (fuseau Europe/Prague) pour connaître la date et l'heure.

2. Pour CHAQUE titre, cherche avec WebSearch les actualités publiées dans les DERNIÈRES 48 HEURES uniquement (vérifie la date de chaque article ; ignore tout ce qui est plus ancien). Sources : presse économique française (Les Échos, Boursorama, Zonebourse, BFM Bourse, ABC Bourse, Investir, Le Revenu, AOF…) ET internationale (Reuters, Bloomberg, Financial Times, WSJ, CNBC, MarketWatch, Handelsblatt ; CoinDesk / The Block pour les cryptos). Privilégie les articles de presse aux notes boursières générées automatiquement. Fais des recherches en français et en anglais.
   Retiens pour chaque titre 0 à 4 faits marquants : résultats, prévisions, contrats, acquisitions, recommandations / objectifs d'analystes, mouvements de cours notables (avec leur raison), réglementation, litiges, dirigeants. Pour Bitcoin et Ethereum : prix et variation, flux ETF, régulation, événements de marché.
   Méthode OBLIGATOIRE pour ne rien manquer — pour CHAQUE titre, fais AU MINIMUM ces 3 recherches séparées :
     a) en anglais avec le nom ET le ticker : "<nom> <ticker> stock news <date du jour>" (ex. "Vistra VST stock news October 21 2026") ;
     b) en anglais : "<nom> price target analyst" (relèvements / abaissements d'objectifs, changements de recommandation) ;
     c) en français : "<nom> action bourse actualité" (ou en allemand pour les valeurs allemandes / autrichiennes : "<nom> Aktie").
   RÈGLE STRICTE : tout titre dont |var_1d_pct| ≥ 3 ne peut PAS rester avec "items": [] — cherche spécifiquement la raison
   ("why <nom> stock up/down today", "<nom> action chute / bondit", "<nom> Aktie fällt / steigt") et indique au moins un fait
   expliquant le mouvement (même s'il s'agit d'un mouvement de secteur ou de marché, dis-le).
   N'oublie pas non plus les suites d'un événement récent encore dans la fenêtre de 48 h (réaction du cours, révisions
   d'objectifs des analystes dans les jours qui suivent une annonce, une augmentation de capital ou des résultats).
   Ne conclus à "aucune info" qu'après ces 3 recherches.
   Si aucune info dans les 48 h : "items": [] — n'invente rien, ne reprends pas d'anciennes infos.

   Exécute aussi `python update_news_gsheet.py --previous` : il liste les infos DÉJÀ publiées pour chaque titre / thème.
   Ne les répète pas (même fait, même s'il est reformulé ou vient d'une autre source) ; n'ajoute que des faits NOUVEAUX.
   Le script de publication fusionne automatiquement : il conserve les anciennes infos et ne garde que les 4 plus récentes
   par carte (les plus anciennes sont retirées en premier). Une carte sans nouveauté garde donc ses infos précédentes.

   AGENDA DES PUBLICATIONS : pour chaque ACTION (pas les cryptos), détermine via l'agenda financier de la société (page
   investisseurs, Zonebourse « agenda », Boursorama, communiqués) :
     - la dernière publication passée (résultats, chiffre d'affaires trimestriel, trading update) : date + libellé ;
     - la prochaine publication : date + libellé + statut "confirmée" (date publiée par la société) ou "estimée"
       (déduite du calendrier habituel, ex. même période que l'an dernier).
   Si la publication annoncée a eu lieu, remplace-la par la suivante (confirmée si connue, sinon estimée).
   Mets-le dans "pub" (voir format). Commence par `python update_news_gsheet.py --previous` qui affiche aussi les "pub" déjà
   connues : ne refais la recherche que si la prochaine date est passée, manquante ou encore "estimée".

2 bis. Marchés & ETF : exécute
   python update_news_gsheet.py --etf-themes
   Il renvoie les ETF / fonds détenus regroupés par THÈME de marché : [{key, label, scope, etfs:[{name, ticker, isin, owner}]}].
   Pour CHAQUE thème (pas pour chaque ETF), cherche les actualités des DERNIÈRES 48 HEURES sur le marché ou le thème décrit
   par "scope" (au minimum 2 recherches : une en anglais, une en français ; ex. "Athens stock exchange Greek banks news",
   "uranium price news", "Bovespa Brazil stocks today", "marchés émergents actualité"). Retiens 0 à 3 faits marquants qui expliquent
   l'évolution de ces ETF : décisions de banques centrales, chiffres macro, mouvements de l'indice et leur raison, événements
   politiques, prix des matières premières, flux.
   Fais aussi UNE recherche par ETF sur les événements propres au fonds (fusion, fermeture, changement d'indice ou de nom,
   baisse de frais, dividende) : ex. "<nom de l'ETF> ISIN <isin>". Ne les signale QUE s'ils datent de moins de 30 jours ;
   sinon n'en parle pas.

3. Écris avec l'outil Write le fichier news_portefeuille.json (UTF-8, dans le dossier courant) :
{
 "generated_at": "<date-heure ISO de Prague, ex. 2026-10-21T07:05+02:00>",
 "summary": "<2-3 phrases : les faits les plus importants pour les titres et ETF dont owner contient \"Seb\">",
 "summary_kids": "<2-3 phrases : les faits les plus importants pour les titres et ETF détenus par les enfants (owner = Estelle, Léandre ou Corentin)>",
 "stocks": [ {"name": "...", "ticker": "...", "kind": "action|crypto", "owner": [...repris de l'étape 1...],
              "items": [ {"sentiment": "pos|neg|neu", "text": "<1-2 phrases, chiffres précis>", "source": "<média>", "url": "<lien de l'article>", "date": "JJ/MM"} ],
              "pub": {"last": {"date": "AAAA-MM-JJ", "label": "<ex. CA T3 2026>"},
                      "next": {"date": "AAAA-MM-JJ", "label": "<ex. Résultats annuels 2026>", "status": "confirmée|estimée"}} } ],
 "themes": [ {"key": "...", "label": "...", "etfs": [...repris tels quels de l'étape 2 bis...],
              "items": [ {"sentiment": "pos|neg|neu", "text": "...", "source": "...", "url": "...", "date": "JJ/MM"} ],
              "fund_events": [ {"etf": "<nom de l'ETF>", "text": "<événement propre au fonds>", "source": "...", "url": "...", "date": "JJ/MM"} ] } ],
 "agenda": [ {"date": "JJ/MM", "text": "<événement de MARCHÉ à venir dans les 15 prochains jours : banques centrales (Fed, BCE…), élections, notations souveraines, chiffres macro, OPEP…>"} ]
   NE METS PAS les publications de résultats / chiffre d'affaires des sociétés dans "agenda" : elles vont uniquement dans "pub".
}
   Un objet par titre de l'étape 1, dans le même ordre, y compris ceux sans info nouvelle (items vide : les anciennes infos sont conservées automatiquement).
   Dans "items", ne mets QUE les faits nouveaux de cette édition (pas ceux listés par --previous).
   Un objet par thème de l'étape 2 bis, dans le même ordre, y compris ceux sans info (items et fund_events vides).
   Le "summary" peut citer un fait de marché important (Fed, BCE…) s'il concerne fortement les ETF.

4. Publie : python update_news_gsheet.py --write news_portefeuille.json
   Le script n'écrit QUE dans l'onglet « News ». Ne modifie aucun autre fichier.

5. Termine par un court compte rendu : nombre de titres et de thèmes avec actualité, les 3 faits principaux. Synthèse indicative, pas un conseil en investissement.
