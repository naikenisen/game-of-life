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

## Vue 3D (Godot) : visiter le monde

Une vue 3D permet de se promener dans le monde pendant que les habitants vivent leur vie :
vue aérienne libre, **mode visiteur** à pied (à hauteur d'yeux, on entre dans les maisons),
ou caméra qui **suit un habitant**. Comme dans les Sims, les toits s'effacent quand on
s'approche pour montrer les intérieurs, un losange coloré indique l'humeur de l'habitant
sélectionné, et sa fiche affiche ses besoins, ses pensées, son plan, son sac et ses souvenirs.

```bash
./run3d.sh --offline          # gratuit, sans LLM (cerveau heuristique)
./run3d.sh                    # avec le LLM (clé dans .env)
./run3d.sh --load             # reprendre la partie sauvegardée
QUALITY=low ./run3d.sh        # qualité graphique : low / medium / high (défaut : automatique)
```

Au premier lancement, le script télécharge les assets (≈120 Mo, CC0, voir
`godot/CREDITS.md`), les importe dans Godot et transfère les animations sur les
personnages (`godot/tools/bake_retarget.gd`). Godot 4.7+ est requis (`GODOT=/chemin/godot`
si l'exécutable n'est pas dans le PATH).

En 3D, la simulation tourne par défaut à 2 ticks/s : les habitants marchent à vitesse
humaine et une journée dure 10 minutes. C'est aussi 5 fois moins d'appels LLM par heure
qu'à la vitesse de la fenêtre 2D. Les boutons ▶ ▶▶ ▶▶▶ accélèrent le temps.

**Commandes** — vue aérienne : ZQSD/flèches, A/E pour tourner, molette pour zoomer,
clic droit glissé pour pivoter. **V** : mode visiteur (souris pour regarder, ZQSD pour
marcher, Maj pour courir). Clic gauche : sélectionner un habitant. **F** : le suivre.
**Tab** : habitant suivant. **R** : toits (auto / visibles / cachés). **Espace** : pause.
**1-4** : vitesse. **H** : aide.

### Vie quotidienne

Les habitants ont des besoins façon Sims : **énergie** (dormir, bien mieux dans un lit),
**vie sociale** (parler, manger ensemble, danser près des autres), **loisirs** (lire,
canapé, repas à table, danse) en plus de la faim et de la santé. L'humeur qui en
découle accélère ou ralentit le travail. Ils peuvent fabriquer des meubles (table, chaise,
tabouret, canapé, bibliothèque, armoire, table de chevet, tapis, lampe, plante, tonneau,
puits), les placer où ils veulent (`furnish` aménage automatiquement une maison) et les
utiliser (`use`) ; `relax` permet de danser, flâner, s'asseoir par terre… Rien de tout
cela n'est imposé : ce sont des possibilités que le LLM choisit ou non.

### Vie intérieure : mémoire, relations, réflexion

Inspirée des « Generative Agents » de Stanford (Park et al., 2023), en version économe :

- **Mémoire à long terme** : chaque souvenir reçoit une importance de 1 à 10 calculée
  par le code (une agression ou une naissance comptent plus qu'un bonjour). À chaque
  décision, le LLM reçoit les souvenirs récents **et** les souvenirs anciens les plus
  utiles maintenant, choisis par récence + importance + pertinence (les personnes
  présentes ou qui lui parlent, les mots en commun avec la situation). La pertinence
  est lexicale plutôt que par embeddings : gratuite.
- **Relations** : chaque habitant a une affinité (-100 à +100) envers chacun, qui
  évolue avec ce qui se passe : parler, donner, échanger, passer du temps ensemble
  rapproche ; refuser un échange, récolter le blé d'un autre, démolir ses murs,
  l'attaquer ou s'en prendre à ses proches éloigne. Les liens familiaux (conjoint,
  parent, enfant) sont mémorisés, et la mort d'un proche est apprise même de loin.
- **Réflexion du soir** : une fois par nuit, si la journée a été riche en événements,
  l'habitant fait le point (un appel LLM court) : il en tire 1 à 3 conclusions
  durables (« je ne peux pas faire confiance à Paul »), une opinion sur les gens qui
  comptent pour lui, et ses objectifs pour les jours suivants. Ces conclusions et
  opinions sont ensuite montrées à chaque décision. Hors-ligne (ou budget atteint, ou
  `--no-reflection`), une version heuristique gratuite les remplace.

Dans la fiche d'un habitant (2D comme 3D) : ses réflexions et ses liens.

### Architecture de la vue 3D

```
lifesim/bridge.py         serveur TCP (JSON par ligne) : terrain, blocs, habitants, animaux, événements
godot/scripts/main.gd     scène : ciel, soleil/lune, lumières, connexion, sélection, minicarte
godot/scripts/terrain.gd  relief, falaises minables, mélange de textures, végétation instanciée
godot/scripts/buildings.gd murs fins raccordés, portes animées, toits à deux pans, planchers, meubles, feux
godot/scripts/person.gd   habitant : modèle habillé, animations, outil en main, déplacements lissés
godot/scripts/animal.gd   animaux animés
godot/scripts/camera_rig.gd caméras aérienne / visiteur / suivi
godot/scripts/hud.gd      interface : barre du haut, fiche habitant, journal, bulles de dialogue
godot/tools/bake_retarget.gd transfert des animations UAL vers le squelette des personnages
tools/fetch_assets.py     téléchargement des assets CC0
```

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
lifesim/mind.py         mémoire à long terme, relations, réflexion du soir
lifesim/simulation.py   boucle, métabolisme, décisions, combat, social, naissances
lifesim/persistence.py  sauvegarde / reprise
lifesim/bridge.py       pont réseau vers la vue 3D Godot
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

La réflexion du soir ajoute au plus un appel court (~1 000 tokens) par habitant et
par jour simulé, seulement après une journée riche en événements : quelques
centimes de l'heure au plus. `--no-reflection` la désactive.

Pour réduire encore : `--think-interval 800`, `--budget 1` (plafond en $, ensuite
cerveau heuristique), ou un modèle moins cher par token (`--model openai/gpt-oss-20b`).
Les journaux complets (prompts, réponses, événements) sont écrits dans `logs/`.
