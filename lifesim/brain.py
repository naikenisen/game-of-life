"""Cerveau heuristique de secours (mode hors-ligne, ou si un appel LLM échoue).

Il produit exactement le même format qu'un LLM. Il reste volontairement simple :
c'est le LLM qui doit rendre les comportements intéressants."""
import random

_rng = random.Random(99)


def _has_station_near(sim, ag, kind, r=25):
    for (x, y), b in sim.world.blocks.items():
        if b.type == kind and abs(x - ag.x) + abs(y - ag.y) <= r:
            return True
    return False


def heuristic_plan(sim, ag):
    inv = ag.inv
    plan = []
    thought = ""
    my_sites = [s for s in sim.structures.values() if s.owner == ag.id]
    paused = [s for s in my_sites if s.status in ("paused", "in_progress", "planned")]
    has_house = any(s.kind == "house" and s.status == "complete" for s in my_sites)

    if ag.hunger < 45 and not ag.food_items():
        thought = "J'ai faim, je cherche à manger."
        plan = [{"action": "gather", "resource": "berries", "amount": 6}, {"action": "eat", "item": "best"}]
    elif sim.is_night() and not has_house:
        thought = "Il fait nuit, je fais un feu."
        if inv.get("campfire", 0) or inv.get("log", 0) >= 4:
            plan = [{"action": "craft", "item": "campfire", "count": 1},
                    {"action": "place", "block": "campfire", "x": ag.x + 1, "y": ag.y}]
        else:
            plan = [{"action": "gather", "resource": "wood", "amount": 5}]
    elif not _has_station_near(sim, ag, "crafting_table") and not inv.get("crafting_table"):
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
                {"action": "craft", "item": "stone_axe", "count": 1}]
    elif paused:
        s = paused[0]
        need = s.needs()
        steps = []
        for mat, n in need.items():
            if mat in ("planks",):
                steps.append({"action": "gather", "resource": "wood", "amount": n // 4 + 2})
                steps.append({"action": "craft", "item": "planks", "count": n})
            elif mat == "cobblestone":
                steps.append({"action": "gather", "resource": "stone", "amount": n})
            elif mat == "door":
                steps.append({"action": "gather", "resource": "wood", "amount": 2})
                steps.append({"action": "craft", "item": "door", "count": 1})
            elif mat == "wheat_seeds":
                steps.append({"action": "gather", "resource": "seeds", "amount": n})
        thought = f"Je termine mon chantier #{s.id}."
        plan = steps[:6] + [{"action": "continue_build", "site_id": s.id}]
    elif not has_house:
        thought = "Je construis une maison en pierre avec un toit en bois."
        x, y = ag.x + _rng.randint(-6, 6), ag.y + _rng.randint(-6, 6)
        plan = [{"action": "gather", "resource": "stone", "amount": 16},
                {"action": "gather", "resource": "wood", "amount": 6},
                {"action": "craft", "item": "door", "count": 1},
                {"action": "build", "structure": "house", "x": x, "y": y, "w": 4, "h": 4,
                 "material": "cobblestone", "roof": "planks", "name": "maison"},
                {"action": "set_home", "x": x + 2, "y": y + 2}]
    else:
        choice = _rng.choice(["food", "iron", "explore", "farm", "talk"])
        if choice == "food":
            thought = "Je fais des réserves de nourriture."
            plan = [{"action": "hunt", "animal": _rng.choice(["cow", "pig", "sheep", "chicken"]), "count": 2},
                    {"action": "craft", "item": "campfire", "count": 1},
                    {"action": "place", "block": "campfire", "x": ag.x, "y": ag.y + 1}]
        elif choice == "iron":
            thought = "Je cherche du fer."
            plan = [{"action": "gather", "resource": "iron", "amount": 4},
                    {"action": "gather", "resource": "coal", "amount": 4}]
        elif choice == "farm" and ag.best_tool("hoe")[0] == 0:
            plan = [{"action": "craft", "item": "stone_hoe", "count": 1},
                    {"action": "gather", "resource": "seeds", "amount": 6}]
        elif choice == "farm":
            plan = [{"action": "build", "structure": "farm", "x": ag.x + 2, "y": ag.y + 2, "w": 3, "h": 3}]
        elif choice == "talk" and sim.perceive(ag)["agents"]:
            other = sim.perceive(ag)["agents"][0][0]
            plan = [{"action": "say", "text": f"Bonjour {other.name} !", "to": other.name}]
        else:
            plan = [{"action": "explore", "direction": "random", "distance": 20}]
    out = {"thought": thought or "…", "plan": plan}
    if has_house and not ag.routine:
        out["routine"] = [{"action": "gather", "resource": "berries", "amount": 4},
                          {"action": "gather", "resource": "wood", "amount": 4},
                          {"action": "harvest", "radius": 12},
                          {"action": "eat", "item": "best"}]
    return out
