"""Cerveau heuristique (mode hors-ligne, budget LLM épuisé, ou appel LLM en échec).

Il produit exactement le même format qu'un LLM. Il donne une vie quotidienne
crédible sans coût (dormir la nuit, travailler, meubler sa maison, discuter,
se détendre), mais c'est le LLM qui rend les comportements vraiment singuliers."""
import random
from . import items as I

_rng = random.Random(99)

GREETINGS = [
    "Bonjour {n} ! Belle journée, non ?", "Salut {n}, tu travailles sur quoi en ce moment ?",
    "{n}, tu as vu les loups cette nuit ?", "Hé {n} ! Ta maison avance bien ?",
    "Bonsoir {n}, on mange ensemble ?", "{n}, il me faudrait de la laine, tu en as ?",
    "Coucou {n} ! J'ai trouvé un coin plein de baies par là.", "{n}, tu veux qu'on construise un puits ensemble ?",
    "Quelle journée... Je suis épuisé(e), {n}.", "{n}, ton jardin est magnifique !",
]
FURNITURE_PLANKS = ["table", "chair", "wardrobe", "nightstand", "chest"]


def _near_block(sim, ag, kind, r=25):
    for (x, y), b in sim.world.blocks.items():
        if b.type == kind and abs(x - ag.x) + abs(y - ag.y) <= r:
            return (x, y)
    return None


def _my_house(sim, ag):
    houses = [s for s in sim.structures.values() if s.owner == ag.id and s.kind == "house" and s.status == "complete"]
    return houses[-1] if houses else None


def _furniture_in(sim, site):
    out = []
    for y in range(site.y + 1, site.y + site.h - 1):
        for x in range(site.x + 1, site.x + site.w - 1):
            b = sim.world.blocks.get((x, y))
            if b is not None:
                out.append(b.type)
    return out


def _social_target(sim, ag):
    """Quelqu'un à qui parler : de préférence une personne appréciée, jamais quelqu'un qu'on déteste."""
    seen = [o for o, _d in sim.perceive(ag)["agents"] if ag.rel.get(o.id, {}).get("aff", 0) > -20]
    if not seen:
        return None
    return max(seen, key=lambda o: ag.rel.get(o.id, {}).get("aff", 0) + _rng.random() * 15)


def heuristic_plan(sim, ag):
    inv = ag.inv
    plan = []
    thought = ""
    out = {}
    my_sites = [s for s in sim.structures.values() if s.owner == ag.id]
    paused = [s for s in my_sites if s.status in ("paused", "in_progress", "planned")]
    house = _my_house(sim, ag)
    night = sim.is_night()

    if ag.hunger < 45 and not ag.food_items():
        thought = "J'ai faim, je cherche à manger."
        prey = _rng.choice(["cow", "pig", "sheep", "chicken"])
        plan = [{"action": "gather", "resource": "berries", "amount": 6}]
        if ag.weapon()[1] >= 3:
            plan.append({"action": "hunt", "animal": prey, "count": 1})
        plan.append({"action": "eat", "item": "best"})
    elif night and house:
        thought = "Il fait nuit, je rentre dormir chez moi."
        cx, cy = house.x + house.w // 2, house.y + house.h // 2
        plan = [{"action": "move_to", "x": cx, "y": cy}]
        if "bed" in _furniture_in(sim, house) or inv.get("bed"):
            if inv.get("bed"):
                plan.append({"action": "furnish", "site_id": house.id, "items": ["bed"]})
        elif ag.fun < 50 and "bookshelf" in _furniture_in(sim, house):
            plan.append({"action": "use", "furniture": "bookshelf", "ticks": 80})
        plan.append({"action": "sleep"})
    elif night and not house:
        thought = "Il fait nuit, je fais un feu."
        if inv.get("campfire", 0) or inv.get("log", 0) >= 4:
            plan = [{"action": "craft", "item": "campfire", "count": 1},
                    {"action": "place", "block": "campfire", "x": ag.x + 1, "y": ag.y},
                    {"action": "use", "furniture": "campfire", "ticks": 100},
                    {"action": "sleep"}]
        else:
            plan = [{"action": "gather", "resource": "wood", "amount": 5}, {"action": "sleep"}]
    elif ag.energy < 12:
        thought = "Je suis épuisé(e), une petite sieste."
        plan = [{"action": "use", "furniture": "bed", "ticks": 200}] if _near_block(sim, ag, "bed", 30) \
            else [{"action": "relax", "activity": "rest", "ticks": 80}]
    elif ag.social < 40 and _social_target(sim, ag):
        other = _social_target(sim, ag)
        liked = ag.rel.get(other.id, {}).get("aff", 0) >= 20
        thought = (f"J'ai envie de voir {other.name}." if liked
                   else f"Je me sens seul(e), je vais parler à {other.name}.")
        plan = [{"action": "say", "to": other.name, "text": _rng.choice(GREETINGS).format(n=other.name)}]
        spare = [k for k in I.FOOD if inv.get(k, 0) >= 4]
        if spare and (liked or _rng.random() < 0.3):
            plan.append({"action": "give", "to": other.name, "items": {_rng.choice(spare): 1}})
        plan.append({"action": "relax", "activity": _rng.choice(["sit", "dance", "watch"]), "ticks": 60})
    elif ag.fun < 30:
        thought = "J'ai besoin de me changer les idées."
        if house and any(f in _furniture_in(sim, house) for f in ("sofa", "bookshelf", "chair")):
            f = _rng.choice([f for f in ("sofa", "bookshelf", "chair") if f in _furniture_in(sim, house)])
            plan = [{"action": "use", "furniture": f, "ticks": 150}]
        else:
            plan = [{"action": "relax", "activity": _rng.choice(["dance", "stroll", "stargaze"]), "ticks": 120}]
    elif not _near_block(sim, ag, "crafting_table") and not inv.get("crafting_table"):
        thought = "Il me faut un établi."
        plan = [{"action": "gather", "resource": "wood", "amount": 6},
                {"action": "craft", "item": "crafting_table", "count": 1},
                {"action": "place", "block": "crafting_table", "x": ag.x + 1, "y": ag.y}]
    elif inv.get("crafting_table"):
        plan = [{"action": "place", "block": "crafting_table", "x": ag.x + 1, "y": ag.y}]
    elif ag.best_tool("pickaxe")[0] == 0:
        thought = "Je fabrique une pioche en bois."
        plan = [{"action": "gather", "resource": "wood", "amount": 3},
                {"action": "craft", "item": "wooden_pickaxe", "count": 1}]
    elif ag.best_tool("pickaxe")[0] < 2:
        thought = "Je vais chercher de la pierre pour de meilleurs outils."
        plan = [{"action": "gather", "resource": "stone", "amount": 12},
                {"action": "gather", "resource": "wood", "amount": 2},
                {"action": "craft", "item": "stone_pickaxe", "count": 1},
                {"action": "craft", "item": "stone_axe", "count": 1},
                {"action": "craft", "item": "stone_sword", "count": 1}]
    elif paused:
        s = paused[0]
        steps = []
        for mat, n in s.needs().items():
            if mat == "planks":
                steps += [{"action": "gather", "resource": "wood", "amount": n // 4 + 2},
                          {"action": "craft", "item": "planks", "count": n}]
            elif mat == "cobblestone":
                steps.append({"action": "gather", "resource": "stone", "amount": n})
            elif mat == "door":
                steps += [{"action": "gather", "resource": "wood", "amount": 2},
                          {"action": "craft", "item": "door", "count": 1}]
            elif mat == "wheat_seeds":
                steps.append({"action": "gather", "resource": "seeds", "amount": n})
        thought = f"Je termine mon chantier #{s.id}."
        plan = steps[:6] + [{"action": "continue_build", "site_id": s.id}]
    elif not house:
        thought = "Je construis ma maison : murs en pierre, toit en bois."
        x, y = ag.x + _rng.randint(-6, 6), ag.y + _rng.randint(-6, 6)
        plan = [{"action": "gather", "resource": "stone", "amount": 18},
                {"action": "gather", "resource": "wood", "amount": 10},
                {"action": "craft", "item": "planks", "count": 34},
                {"action": "craft", "item": "door", "count": 1},
                {"action": "build", "structure": "house", "x": x, "y": y, "w": 6, "h": 5,
                 "material": "cobblestone", "roof": "planks", "name": f"maison de {ag.name}"},
                {"action": "set_home", "x": x + 3, "y": y + 2}]
    else:
        have = _furniture_in(sim, house)
        missing_planks = [f for f in FURNITURE_PLANKS if f not in have]
        if missing_planks and len(have) < 8:
            thought = "Je meuble ma maison."
            plan = [{"action": "gather", "resource": "wood", "amount": 6}]
            plan += [{"action": "craft", "item": f, "count": 1} for f in missing_planks[:3] if not inv.get(f)]
            plan.append({"action": "furnish", "site_id": house.id, "items": missing_planks[:3]})
        elif "bed" not in have:
            thought = "Il me faut un vrai lit : de la laine de mouton."
            plan = [{"action": "hunt", "animal": "sheep", "count": 2},
                    {"action": "gather", "resource": "wood", "amount": 2},
                    {"action": "craft", "item": "bed", "count": 1},
                    {"action": "furnish", "site_id": house.id, "items": ["bed"]}]
        elif "bookshelf" not in have or "sofa" not in have:
            thought = "Un peu de confort : canapé et bibliothèque."
            plan = [{"action": "hunt", "animal": _rng.choice(["cow", "sheep"]), "count": 2},
                    {"action": "gather", "resource": "wood", "amount": 4},
                    {"action": "furnish", "site_id": house.id, "items": ["sofa", "bookshelf", "rug"]}]
        else:
            choice = _rng.choice(["food", "farm", "explore", "visit", "work"])
            if choice == "food":
                thought = "Je fais des réserves de nourriture."
                plan = [{"action": "hunt", "animal": _rng.choice(["cow", "pig", "sheep", "chicken"]), "count": 2},
                        {"action": "craft", "item": "cooked_beef", "count": 1},
                        {"action": "eat", "item": "best"}]
            elif choice == "farm" and ag.best_tool("hoe")[0] == 0:
                plan = [{"action": "craft", "item": "stone_hoe", "count": 1},
                        {"action": "gather", "resource": "seeds", "amount": 9}]
            elif choice == "farm":
                thought = "Je cultive un petit champ de blé."
                plan = [{"action": "gather", "resource": "seeds", "amount": 9},
                        {"action": "build", "structure": "farm", "x": house.x + house.w + 1, "y": house.y,
                         "w": 3, "h": 3}]
            elif choice == "visit" and sim.perceive(ag)["agents"]:
                other = sim.perceive(ag)["agents"][-1][0]
                thought = f"Je rends visite à {other.name}."
                plan = [{"action": "go_to", "target": other.name},
                        {"action": "say", "to": other.name, "text": _rng.choice(GREETINGS).format(n=other.name)}]
            elif choice == "work":
                thought = "Au travail."
                plan = [{"action": "gather", "resource": _rng.choice(["wood", "stone", "iron", "coal"]), "amount": 6}]
            else:
                plan = [{"action": "explore", "direction": "random", "distance": 20}]
        if not ag.routine:
            out["routine"] = [{"action": "gather", "resource": "berries", "amount": 4},
                              {"action": "gather", "resource": "wood", "amount": 4},
                              {"action": "harvest", "radius": 12},
                              {"action": "eat", "item": "best"},
                              {"action": "use", "furniture": "sofa", "ticks": 80}]
    out.update({"thought": thought or "…", "plan": plan})
    return out
