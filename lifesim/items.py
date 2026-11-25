"""Données du jeu : objets, outils, nourriture, blocs posables et recettes.

Tout est déclaratif : ajouter une recette ou un bloc ici suffit pour que les
agents (et le LLM, via le prompt) puissent l'utiliser.
"""

# --------------------------------------------------------------------------
# Nourriture : item -> points de faim rendus
# --------------------------------------------------------------------------
FOOD = {
    "berries": 6,
    "apple": 8,
    "raw_beef": 8,
    "raw_pork": 8,
    "raw_mutton": 7,
    "raw_chicken": 4,
    "raw_fish": 5,
    "cooked_beef": 20,
    "cooked_pork": 20,
    "cooked_mutton": 16,
    "cooked_chicken": 14,
    "cooked_fish": 14,
    "bread": 15,
    "egg": 3,
    "bowl_stew": 18,
}

# --------------------------------------------------------------------------
# Outils / armes / armures
# --------------------------------------------------------------------------
TIERS = {"wooden": 1, "stone": 2, "iron": 3, "diamond": 4}

# kind -> {item: tier}
TOOLS = {
    "pickaxe": {f"{t}_pickaxe": v for t, v in TIERS.items()},
    "axe": {f"{t}_axe": v for t, v in TIERS.items()},
    "shovel": {f"{t}_shovel": v for t, v in TIERS.items()},
    "hoe": {f"{t}_hoe": v for t, v in TIERS.items()},
}
TOOLS["shears"] = {"shears": 3}
TOOLS["fishing_rod"] = {"fishing_rod": 1}

# dégâts de mêlée (le poing fait 1)
MELEE_DAMAGE = {
    "wooden_sword": 4, "stone_sword": 5, "iron_sword": 6, "diamond_sword": 7,
    "wooden_axe": 3, "stone_axe": 4, "iron_axe": 5, "diamond_axe": 6,
    "spear": 5,
}
# armes à distance : item -> (dégâts, portée, munition)
RANGED = {
    "bow": (6, 8, "arrow"),
}
# armures : item -> réduction des dégâts (0..1)
ARMOR = {
    "leather_armor": 0.25,
    "iron_armor": 0.5,
    "diamond_armor": 0.65,
}
SHIELD = {"shield": 0.3}  # réduction supplémentaire

# --------------------------------------------------------------------------
# Blocs posables dans le monde
#   solid      : bloque les agents
#   blocks_animals : bloque les animaux
#   hp         : points de structure (pour la démolition)
#   station    : sert de poste de fabrication
#   light      : réchauffe/éclaire la nuit dans ce rayon
# --------------------------------------------------------------------------
BLOCKS = {
    "planks":         dict(solid=True,  blocks_animals=True, hp=30, color=(176, 132, 72)),
    "log":            dict(solid=True,  blocks_animals=True, hp=40, color=(120, 85, 45)),
    "cobblestone":    dict(solid=True,  blocks_animals=True, hp=70, color=(120, 120, 125)),
    "brick":          dict(solid=True,  blocks_animals=True, hp=90, color=(160, 70, 55)),
    "glass":          dict(solid=True,  blocks_animals=True, hp=10, color=(190, 230, 240)),
    "iron_block":     dict(solid=True,  blocks_animals=True, hp=200, color=(210, 210, 215)),
    "fence":          dict(solid=True,  blocks_animals=True, hp=20, color=(150, 110, 60)),
    "fence_gate":     dict(solid=False, blocks_animals=True, hp=20, color=(185, 140, 80)),
    "door":           dict(solid=False, blocks_animals=True, hp=25, color=(110, 70, 35)),
    "iron_door":      dict(solid=False, blocks_animals=True, hp=150, color=(180, 180, 190), locked=True),
    "crafting_table": dict(solid=True,  blocks_animals=True, hp=20, color=(150, 95, 50), station=True),
    "furnace":        dict(solid=True,  blocks_animals=True, hp=50, color=(80, 80, 85), station=True, light=2),
    "anvil":          dict(solid=True,  blocks_animals=True, hp=150, color=(60, 60, 70), station=True),
    "chest":          dict(solid=True,  blocks_animals=True, hp=20, color=(200, 150, 60)),
    "bed":            dict(solid=False, blocks_animals=False, hp=10, color=(200, 40, 40)),
    "torch":          dict(solid=False, blocks_animals=False, hp=1, color=(255, 210, 80), light=4),
    "campfire":       dict(solid=True,  blocks_animals=True, hp=10, color=(255, 120, 30), station=True, light=5),
    "scarecrow":      dict(solid=True,  blocks_animals=True, hp=10, color=(220, 200, 120)),
    "sign":           dict(solid=False, blocks_animals=False, hp=5, color=(190, 160, 110)),
    "trap":           dict(solid=False, blocks_animals=False, hp=10, color=(90, 90, 90), trap_damage=6),
    # --- mobilier (vie quotidienne) ; use = ce qu'on peut y faire avec l'action use()
    "table":          dict(solid=True,  blocks_animals=True, hp=15, color=(160, 110, 60), furniture=True, use="eat"),
    "chair":          dict(solid=False, blocks_animals=True, hp=8,  color=(150, 100, 55), furniture=True, use="sit"),
    "stool":          dict(solid=False, blocks_animals=True, hp=6,  color=(150, 105, 60), furniture=True, use="sit"),
    "sofa":           dict(solid=False, blocks_animals=True, hp=12, color=(120, 60, 60), furniture=True, use="sit"),
    "bookshelf":      dict(solid=True,  blocks_animals=True, hp=15, color=(110, 75, 40), furniture=True, use="read"),
    "wardrobe":       dict(solid=True,  blocks_animals=True, hp=15, color=(130, 90, 50), furniture=True, use="dress"),
    "nightstand":     dict(solid=True,  blocks_animals=True, hp=8,  color=(140, 95, 55), furniture=True),
    "rug":            dict(solid=False, blocks_animals=False, hp=4, color=(170, 60, 70), furniture=True),
    "lamp":           dict(solid=True,  blocks_animals=True, hp=6,  color=(250, 230, 160), furniture=True, light=3),
    "plant_pot":      dict(solid=True,  blocks_animals=True, hp=4,  color=(80, 150, 70), furniture=True),
    "barrel":         dict(solid=True,  blocks_animals=True, hp=15, color=(120, 80, 45), furniture=True),
    "well":           dict(solid=True,  blocks_animals=True, hp=60, color=(110, 110, 120), use="drink"),
}

# matériaux utilisables pour un toit (1 unité par case couverte)
ROOF_MATERIALS = ["planks", "cobblestone", "brick", "glass", "log"]

# --------------------------------------------------------------------------
# Recettes
#   station : None (à la main), "crafting_table", "furnace", "anvil" ou "campfire"
#   (furnace et campfire peuvent cuire ; seul le furnace fond le minerai)
# --------------------------------------------------------------------------
RECIPES = {}


def _r(name, out, inputs, station=None):
    RECIPES[name] = {"out": out, "in": inputs, "station": station}


# bois
_r("planks", 4, {"log": 1})
_r("stick", 4, {"planks": 2})
_r("crafting_table", 1, {"planks": 4})
_r("string", 1, {"fiber": 3})
_r("rope_lead", 1, {"string": 2})
_r("torch", 4, {"stick": 1, "coal": 1})
_r("torch_charcoal", 4, {"stick": 1, "charcoal": 1})
_r("campfire", 1, {"log": 3, "stick": 3})
_r("sign", 1, {"planks": 2, "stick": 1})
_r("chest", 1, {"planks": 8}, "crafting_table")
_r("fence", 3, {"planks": 4, "stick": 2}, "crafting_table")
_r("fence_gate", 1, {"planks": 2, "stick": 4}, "crafting_table")
_r("door", 1, {"planks": 6}, "crafting_table")
_r("bed", 1, {"wool": 3, "planks": 3}, "crafting_table")
_r("boat", 1, {"planks": 5}, "crafting_table")
_r("scarecrow", 1, {"stick": 3, "fiber": 4}, "crafting_table")
_r("trap", 1, {"planks": 2, "iron_ingot": 1, "string": 1}, "crafting_table")
_r("furnace", 1, {"cobblestone": 8}, "crafting_table")
_r("anvil", 1, {"iron_ingot": 6}, "crafting_table")
_r("iron_block", 1, {"iron_ingot": 4}, "anvil")
_r("iron_door", 1, {"iron_ingot": 6}, "anvil")
_r("bucket", 1, {"iron_ingot": 3}, "crafting_table")
_r("shears", 1, {"iron_ingot": 2}, "crafting_table")
_r("fishing_rod", 1, {"stick": 3, "string": 2}, "crafting_table")
_r("bow", 1, {"stick": 3, "string": 3}, "crafting_table")
_r("arrow", 4, {"stick": 1, "flint": 1, "feather": 1}, "crafting_table")
_r("spear", 1, {"stick": 2, "flint": 2}, "crafting_table")
_r("shield", 1, {"planks": 6, "iron_ingot": 1}, "crafting_table")
_r("leather_armor", 1, {"leather": 6}, "crafting_table")
_r("iron_armor", 1, {"iron_ingot": 8}, "anvil")
_r("diamond_armor", 1, {"diamond": 8}, "anvil")
_r("bread", 1, {"wheat": 3}, "crafting_table")
# mobilier
_r("table", 1, {"planks": 4, "stick": 2}, "crafting_table")
_r("chair", 1, {"planks": 3, "stick": 2}, "crafting_table")
_r("stool", 1, {"planks": 2, "stick": 1}, "crafting_table")
_r("sofa", 1, {"planks": 4, "wool": 3}, "crafting_table")
_r("bookshelf", 1, {"planks": 6, "leather": 1}, "crafting_table")
_r("wardrobe", 1, {"planks": 8}, "crafting_table")
_r("nightstand", 1, {"planks": 3}, "crafting_table")
_r("rug", 1, {"wool": 4})
_r("lamp", 1, {"iron_ingot": 1, "glass": 1, "torch": 1}, "crafting_table")
_r("plant_pot", 1, {"clay": 2, "sapling": 1})
_r("barrel", 1, {"planks": 6, "iron_ingot": 1}, "crafting_table")
_r("well", 1, {"cobblestone": 12, "planks": 4, "rope_lead": 1}, "crafting_table")
_r("bowl_stew", 1, {"raw_mushroom": 2, "stick": 1}, "cook")
_r("bone_meal", 3, {"bone": 1})

# outils par tier
_MATERIAL_FOR = {"wooden": "planks", "stone": "cobblestone", "iron": "iron_ingot", "diamond": "diamond"}
for tier, mat in _MATERIAL_FOR.items():
    st = "crafting_table" if tier != "diamond" else "anvil"
    _r(f"{tier}_pickaxe", 1, {mat: 3, "stick": 2}, st)
    _r(f"{tier}_axe", 1, {mat: 3, "stick": 2}, st)
    _r(f"{tier}_shovel", 1, {mat: 1, "stick": 2}, st)
    _r(f"{tier}_hoe", 1, {mat: 2, "stick": 2}, st)
    _r(f"{tier}_sword", 1, {mat: 2, "stick": 1}, st)

# fonte / cuisson
_r("iron_ingot", 1, {"iron_ore": 1, "fuel": 1}, "furnace")
_r("gold_ingot", 1, {"gold_ore": 1, "fuel": 1}, "furnace")
_r("glass", 1, {"sand": 1, "fuel": 1}, "furnace")
_r("brick", 1, {"clay": 1, "fuel": 1}, "furnace")
_r("charcoal", 1, {"log": 1, "fuel": 1}, "furnace")
for raw in ("beef", "pork", "mutton", "chicken", "fish"):
    _r(f"cooked_{raw}", 1, {f"raw_{raw}": 1, "fuel": 1}, "cook")

# items qui comptent comme combustible pour l'entrée virtuelle "fuel"
FUEL_ITEMS = ["coal", "charcoal", "log", "planks", "stick"]

# Le nom de recette diffère parfois du nom de l'objet produit
RECIPE_OUTPUT_ITEM = {"torch_charcoal": "torch"}


def recipe_output_item(recipe_name):
    return RECIPE_OUTPUT_ITEM.get(recipe_name, recipe_name)


# --------------------------------------------------------------------------
# Ressources récoltables (action gather) : nom -> description pour le prompt
# --------------------------------------------------------------------------
GATHERABLE = {
    "wood": "chop trees -> log (+ sometimes apple, sapling). Axe makes it faster.",
    "stone": "mine rock -> cobblestone (+ sometimes flint). Needs any pickaxe.",
    "coal": "mine coal ore -> coal. Needs any pickaxe.",
    "iron": "mine iron ore -> iron_ore. Needs stone pickaxe or better.",
    "gold": "mine gold ore -> gold_ore. Needs iron pickaxe or better.",
    "diamond": "mine diamond ore -> diamond. Needs iron pickaxe or better.",
    "berries": "pick berry bushes -> berries (bushes regrow).",
    "fiber": "cut tall grass -> fiber (+ sometimes wheat seeds).",
    "seeds": "same as fiber, but keeps going until enough seeds.",
    "sand": "dig sand -> sand. Shovel makes it faster.",
    "clay": "dig clay near water -> clay. Shovel makes it faster.",
    "mushroom": "pick mushrooms in forests -> raw_mushroom.",
    "flint": "dig gravel -> flint. Shovel makes it faster.",
}

ANIMALS = {
    # espèce : hp, vitesse(ticks par pas), drops, hostile
    "sheep":   dict(hp=8,  speed=4, drops={"raw_mutton": 2, "wool": 2}, hostile=False, color=(235, 235, 235)),
    "cow":     dict(hp=10, speed=5, drops={"raw_beef": 3, "leather": 2}, hostile=False, color=(110, 75, 50)),
    "pig":     dict(hp=10, speed=4, drops={"raw_pork": 3}, hostile=False, color=(240, 160, 170)),
    "chicken": dict(hp=4,  speed=3, drops={"raw_chicken": 1, "feather": 2}, hostile=False, color=(250, 240, 120)),
    "wolf":    dict(hp=10, speed=2, drops={"bone": 2}, hostile=True, color=(80, 80, 90), damage=2),
}


def all_item_names():
    names = set(FOOD) | set(BLOCKS) | set(MELEE_DAMAGE) | set(RANGED) | set(ARMOR) | set(SHIELD)
    for kind in TOOLS.values():
        names |= set(kind)
    for name, r in RECIPES.items():
        names.add(recipe_output_item(name))
        names |= set(r["in"])
    for a in ANIMALS.values():
        names |= set(a["drops"])
    names |= {"log", "cobblestone", "coal", "iron_ore", "gold_ore", "diamond", "flint", "sapling",
              "wheat_seeds", "wheat", "fiber", "sand", "clay", "raw_mushroom", "bucket", "water_bucket"}
    names.discard("fuel")
    return sorted(names)


def recipes_prompt_text():
    """Liste compacte des recettes pour le prompt système."""
    lines = []
    for name, r in RECIPES.items():
        ins = " + ".join(f"{n} {k}" for k, n in r["in"].items())
        st = r["station"]
        where = "" if st is None else (" @furnace or campfire" if st == "cook" else f" @{st}")
        out_item = recipe_output_item(name)
        alias = f" (recipe '{name}')" if out_item != name else ""
        lines.append(f"- {r['out']} {out_item}{alias} <- {ins}{where}")
    return "\n".join(lines)
