# LifeSim — une simulation de vie pilotée par des LLM

Un territoire vu de dessus, des ressources façon Minecraft, et 30 habitants qui
décident eux-mêmes de leur vie. Chaque habitant appelle un petit LLM (via
[OpenRouter](https://openrouter.ai)) pour ses **décisions stratégiques** :
« j'ai 100 pierres → je construis les murs de ma maison en (40,22), ensuite je
vais chercher du bois pour le toit ». Tout le reste — marcher, trouver un chemin,
couper les arbres, poser les blocs un par un, se battre — est exécuté par des
algorithmes.

Rien n'est imposé aux habitants : on ne leur dit **pas** de faire une ferme,
d'élever des animaux ou d'attaquer leurs voisins. Les règles du monde le
**permettent**, et c'est le LLM qui décide.

## Lancer

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

La clé est lue dans `.env` :

```
OPENROUTER_API_KEY=sk-or-...
# optionnel : LLM_MODEL=mistralai/mistral-small-3.2-24b-instruct
```

### Sauvegarde et reprise

La partie est sauvegardée automatiquement dans `saves/world.pkl` toutes les 5 minutes
et à la fermeture (fenêtre ou Ctrl+C), et à la demande avec **F5**. Pour reprendre :

```bash
.venv/bin/python main.py --load
```

Tout est conservé : terrain modifié, constructions, champs, coffres, animaux, et pour
chaque habitant son inventaire, sa mémoire, ses notes, son plan et sa routine.
Seule l'étape en cours redémarre au début (le chantier, lui, garde sa progression).
Lancer **sans** `--load` crée un nouveau monde ; l'ancienne sauvegarde n'est pas
perdue, elle est renommée `saves/world_<date>.pkl` (reprise avec `--load saves/world_<date>.pkl`).
Ne chargez que vos propres sauvegardes (format pickle).

Options utiles :

| option | rôle |
|---|---|
| `--model ID` | modèle OpenRouter (défaut `mistralai/mistral-small-3.2-24b-instruct`) |
| `--agents N` | nombre d'habitants au départ (défaut 30) |
| `--budget 2.0` | plafond de dépense LLM en $ ; au-delà, un cerveau heuristique prend le relais |
| `--load [FICHIER]` | reprendre une partie (défaut `saves/world.pkl`) |
| `--save FICHIER` / `--no-save` | où sauvegarder / ne pas sauvegarder |
| `--offline` | aucun appel LLM (cerveau heuristique simple), pour tester |
| `--headless --ticks 3000` | sans fenêtre, affiche les événements dans le terminal |
| `--screenshot carte.png` | (avec `--headless`) enregistre une image de la carte à la fin |
| `--seed N`, `--width`, `--height` | génération du monde |
| `--tps N` | ticks par seconde à vitesse x1 (défaut 10) |
| `--concurrency N` | appels LLM simultanés (défaut 12) |
| `--think-interval N` | ticks minimum avant de ré-interroger un habitant occupé (défaut 400) |
| `--language English` | langue des pensées et dialogues |

### Commandes dans la fenêtre

- **clic gauche** sur un habitant : voir ses pensées, son plan, son inventaire, ses notes, sa mémoire
- **clic droit / molette-clic glissé** : déplacer la carte, **molette** : zoom
- **Tab** : habitant suivant, **F** : suivre la caméra, **Échap** : désélectionner
- **Espace** : pause, **+ / -** : vitesse (x0.25 à x32), **R** : afficher/masquer les toits, **H** : aide
- **F5** : sauvegarder

## Le monde

- **Terrain** généré par bruit : lacs, plages (sable, argile, gravier), prairies,
  forêts (arbres, champignons, baies), montagnes de roche avec minerais
  (charbon, fer, or, diamant). La roche bloque le passage tant qu'elle n'est pas minée.
- **Cycle jour/nuit** : la nuit, rester dehors sans toit ni source de lumière fait
  perdre de la vie, et les loups chassent.
- **Survie** : faim, points de vie, mort définitive (l'inventaire tombe au sol).
- **Repousse** : les arbres repoussent depuis les pousses, les buissons de baies et l'herbe repoussent.
- **Animaux** : moutons, vaches, cochons, poules errent ; ils ne franchissent ni
  murs, ni clôtures, ni portes, ni portillons. On peut les chasser, les mener en
  laisse, les faire se reproduire, tondre les moutons ; les poules pondent.
  Les loups sont dangereux mais s'apprivoisent avec des os.

### Ce que les habitants peuvent faire (37 actions)

Se déplacer, explorer, récolter (bois, pierre, minerais, baies, fibres, graines,
sable, argile, silex…), **fabriquer** (≈ 75 recettes : outils en bois/pierre/fer/diamant,
épées, lance, arc et flèches, armures, bouclier, four, enclume, coffre, lit,
portes, clôtures, torches, pièges, bateau, pain, viande cuite…), **construire**
(maison, enclos, mur, champ, toit, ou forme libre case par case), poser/détruire
n'importe quel bloc, cultiver et récolter le blé, chasser, **attaquer** une
personne, fuir, mener un animal en laisse, élever, tondre, apprivoiser, pêcher,
parler, donner, **proposer/accepter des échanges**, stocker/prendre dans des coffres
(y compris ceux des autres), dormir, poser des panneaux, verrouiller une porte en fer,
avoir un enfant à deux…

La propriété n'est **pas** protégée par le monde : tout le monde peut démolir,
voler dans un coffre ou récolter le champ d'autrui. Les témoins s'en souviennent.

## Architecture

```
main.py                 point d'entrée (fenêtre ou headless)
lifesim/config.py       paramètres
lifesim/items.py        objets, outils, armes, blocs, recettes (déclaratif)
lifesim/world.py        terrain, ressources, blocs, toits, cultures, A*
lifesim/animals.py      faune : errance, fuite, laisse, loups, reproduction
lifesim/blueprints.py   plans de construction -> liste de cases à poser
lifesim/actions.py      exécution algorithmique de chaque action (générateurs tick par tick)
lifesim/agent.py        état d'un habitant
lifesim/llm.py          prompt, appel OpenRouter (threads), parsing JSON
lifesim/brain.py        cerveau heuristique de secours (hors-ligne / erreur LLM)
lifesim/simulation.py   boucle, métabolisme, décisions, combat, social, naissances
lifesim/persistence.py  sauvegarde / reprise
lifesim/render.py       affichage pygame
```

**Quand le LLM est-il appelé ?** Le moins souvent possible, pour qu'un monde
vive des heures sans coûter cher :

- chaque décision est un **plan long** (jusqu'à 15 étapes) ;
- le LLM peut fixer une **routine** (jusqu'à 10 étapes, par ex. « récolter le blé →
  replanter → stocker au coffre → chasser ») que l'habitant répète **seul**, en boucle,
  sans aucun appel ;
- l'échec d'une étape secondaire (parler, donner, échanger, manger, suivre…) ne
  coupe pas le plan ;
- les simples informations (« X t'a donné 3 bûches ») sont gardées pour la
  prochaine décision au lieu de déclencher un appel.

Le LLM est donc rappelé seulement quand : le plan est fini et il n'y a pas de
routine, une étape importante échoue (ou la routine échoue 2 fois de suite), il
est attaqué, quelqu'un lui parle directement, on lui propose un échange ou un
enfant, ou au plus tard toutes les 4000 ticks. Un habitant occupé n'est jamais
ré-interrogé plus d'une fois toutes les 400 ticks (`--think-interval` pour
changer ce délai). Les appels sont asynchrones (pool de threads) : la simulation
ne s'arrête jamais en attendant une réponse. En cas d'attaque, un réflexe
immédiat (riposter si armé, sinon fuir) s'applique en attendant la décision.

Le LLM répond en JSON : une pensée, éventuellement une phrase prononcée, des
notes personnelles à long terme, un plan, et éventuellement une routine.

**Ajouter du contenu** : une recette ou un bloc dans `items.py` est automatiquement
connu du jeu et décrit au LLM dans le prompt.

## Choix du modèle (petits LLM, réponses rapides)

Les décisions sont prises par de **petits modèles sans phase de raisonnement**
(le raisonnement est désactivé dans la requête). Mesures sur un vrai prompt d'habitant :

| modèle | latence | remarque |
|---|---|---|
| `mistralai/mistral-small-3.2-24b-instruct` (défaut) | 3–4 s | le plus fiable (JSON propre, plans cohérents, français) |
| `meta-llama/llama-3.1-8b-instruct` | ~1 s | le plus rapide, plans parfois moins cohérents |
| `openai/gpt-oss-20b` | ~6 s | très bon marché |
| `google/gemma-3-12b-it` | ~5 s | correct |

De toute façon, les appels sont **asynchrones** : la simulation n'attend jamais
le LLM, l'habitant continue son plan en cours pendant qu'il « réfléchit » (point
bleu au-dessus de lui).

## Coût

Le coût dépend surtout du **nombre de décisions** (chaque appel envoie ~4 400 tokens
de contexte). Avant l'ajout des plans longs et des routines, 30 habitants
coûtaient environ 2,5 $ de l'heure à vitesse x1 (mesuré). Ces mécanismes divisent
le nombre de décisions par environ 3 en test hors-ligne ; le coût réel avec le
LLM n'a pas encore été remesuré. Le coût est proportionnel à la vitesse de la
simulation (x4 = 4 fois plus d'appels par heure réelle).

Pour réduire encore : `--think-interval 800`, `--budget 1` (plafond en $, ensuite
cerveau heuristique), ou un modèle moins cher par token (`--model openai/gpt-oss-20b`).
Les journaux complets (prompts, réponses, événements) sont écrits dans `logs/`.
