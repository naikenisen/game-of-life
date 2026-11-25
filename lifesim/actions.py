"""Exécution algorithmique des étapes d'un plan.

Chaque action est un générateur : il fait `yield` à chaque tick tant qu'il travaille,
lève ActionFailed(raison) en cas d'échec, et renvoie (return) un texte de résultat.
"""
import math
import random

from . import blueprints as BP
from . import items as I
from . import world as W
from .animals import Animal


class ActionFailed(Exception):
    pass


rng = random.Random(1234)


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _int(p, k, default=0):
    try:
        return int(p.get(k, default))
    except (TypeError, ValueError):
        return default


ITEM_ALIASES = {"wood": "log", "logs": "log", "stone": "cobblestone", "stones": "cobblestone",
                "eggs": "egg", "berry": "berries", "seeds": "wheat_seeds", "seed": "wheat_seeds",
                "plank": "planks", "sticks": "stick", "torches": "torch", "arrows": "arrow",
                "mushroom": "raw_mushroom", "mushrooms": "raw_mushroom", "fish": "raw_fish", "coals": "coal"}


def norm_item(name):
    n = str(name).strip().lower().replace(" ", "_")
    return ITEM_ALIASES.get(n, n)


def _count_dict(v):
    """{'log': 3} ou [['log',3]] ou 'log:3' ou {'item': 'log', 'count': 3} -> dict"""
    out = {}
    if isinstance(v, dict) and "item" in v:
        v = {v["item"]: v.get("count", v.get("amount", 1))}
    if isinstance(v, list) and v and all(isinstance(e, dict) and "item" in e for e in v):
        v = {e["item"]: e.get("count", e.get("amount", 1)) for e in v}
    if isinstance(v, dict):
        for k, n in v.items():
            try:
                out[str(k)] = int(n)
            except (TypeError, ValueError):
                pass
    elif isinstance(v, list):
        for e in v:
            if isinstance(e, (list, tuple)) and len(e) == 2:
                out[str(e[0])] = int(e[1])
    elif isinstance(v, str) and v:
        for part in v.split(","):
            if ":" in part:
                k, n = part.split(":", 1)
                out[k.strip()] = int(n)
    return {norm_item(k): n for k, n in out.items() if n > 0}


# ============================================================== déplacement
def enclosed_hint(sim, ag, limit=150):
    """Si l'agent ne peut atteindre qu'une petite zone, renvoie un conseil (sinon "")."""
    w = sim.world
    seen = {ag.pos}
    stack = [ag.pos]
    while stack and len(seen) < limit:
        x, y = stack.pop()
        for n in w.neighbors4(x, y):
            if n not in seen and w.passable(n[0], n[1], ag.id, ag.has_boat):
                seen.add(n)
                stack.append(n)
    if len(seen) >= limit:
        return ""
    blocks = [p for p in {nb for c in seen for nb in w.neighbors4(*c)} - seen if p in w.blocks]
    ex = f" e.g. demolish(x={blocks[0][0]}, y={blocks[0][1]})" if blocks else ""
    return f" — you are ENCLOSED in a small area of {len(seen)} tiles: demolish a block to get out{ex}"


def walk_to(sim, ag, goals, max_ticks=3000):
    goals = set(goals)
    if not goals:
        raise ActionFailed("no reachable destination")
    spent = 0
    replans = 0
    while ag.pos not in goals:
        path = sim.world.find_path(ag.pos, goals, ag.id, ag.has_boat)
        if path is None:
            raise ActionFailed("no path to destination" + enclosed_hint(sim, ag))
        for step in path:
            if not sim.world.passable(step[0], step[1], ag.id, ag.has_boat):
                break  # quelque chose a été construit sur le chemin : on recalcule
            cost = sim.world.move_cost(*step)
            for _ in range(int(round(cost)) - 1):
                spent += 1
                yield
            ag.x, ag.y = step
            spent += 1
            yield
            if spent > max_ticks:
                raise ActionFailed("journey took too long")
        replans += 1
        if replans > 8 and ag.pos not in goals:
            raise ActionFailed("path keeps getting blocked")


def walk_adjacent(sim, ag, x, y, max_ticks=3000):
    if manhattan(ag.pos, (x, y)) <= 1:
        return
    goals = sim.world.adjacent_goals(x, y, ag.id, ag.has_boat)
    if sim.world.passable(x, y, ag.id, ag.has_boat):
        goals.add((x, y))
    yield from walk_to(sim, ag, goals, max_ticks)


def walk_within(sim, ag, x, y, r, max_ticks=3000):
    if cheb(ag.pos, (x, y)) <= r:
        return
    goals = set()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            nx, ny = x + dx, y + dy
            if sim.world.passable(nx, ny, ag.id, ag.has_boat):
                goals.add((nx, ny))
    yield from walk_to(sim, ag, goals, max_ticks)


def wait(n):
    for _ in range(max(0, int(n))):
        yield


def work_time(base, tier):
    return max(2, int(base / (1 + 0.8 * tier)))


# ============================================================== actions de base
def act_move_to(sim, ag, p):
    x, y = _int(p, "x", ag.x), _int(p, "y", ag.y)
    x = max(0, min(sim.world.w - 1, x))
    y = max(0, min(sim.world.h - 1, y))
    if sim.world.passable(x, y, ag.id, ag.has_boat):
        yield from walk_to(sim, ag, {(x, y)})
    else:
        target = sim.world.find_nearest(x, y, lambda a, b: sim.world.passable(a, b, ag.id, ag.has_boat), 6)
        if target is None:
            raise ActionFailed(f"({x},{y}) is not walkable")
        yield from walk_to(sim, ag, {target})
    return f"arrived at {ag.pos}"


def act_go_to(sim, ag, p):
    t = str(p.get("target", "")).strip()
    low = t.lower()
    for prefix in ("person:", "agent:", "resource:", "block:"):
        if low.startswith(prefix):
            t = t[len(prefix):]
            low = t.lower()
    if low == "home":
        if not ag.home:
            raise ActionFailed("you have no home set (use set_home)")
        return (yield from act_move_to(sim, ag, {"x": ag.home[0], "y": ag.home[1]}))
    # coordonnées "x,y"
    if "," in low and all(part.strip().lstrip("-").isdigit() for part in low.split(",")[:2]):
        x, y = (int(v) for v in low.split(",")[:2])
        return (yield from act_move_to(sim, ag, {"x": x, "y": y}))
    if low.startswith("structure:") or low.startswith("#") or low.startswith("site"):
        raw = low.split(":")[-1].lstrip("#").replace("site", "").strip()
        if raw.isdigit():
            s = sim.structures.get(int(raw))
            if not s:
                raise ActionFailed(f"unknown structure {t}")
            yield from walk_within(sim, ag, s.x + s.w // 2, s.y + s.h // 2, max(s.w, s.h) // 2 + 1)
            return f"arrived near structure #{s.id}"
        low = raw
    other = sim.find_agent(t)
    if other is not None:
        yield from follow_agent(sim, ag, other, until_adjacent=True)
        return f"reached {other.name}"
    # type de bloc (le plus proche)
    if low in I.BLOCKS:
        best = None
        for pos, b in sim.world.blocks.items():
            if b.type == low:
                d = manhattan(pos, ag.pos)
                if best is None or d < best[0]:
                    best = (d, pos)
        if best is None:
            raise ActionFailed(f"no {low} known in the world")
        yield from walk_adjacent(sim, ag, *best[1])
        return f"arrived next to the {low} at {best[1]}"
    # ressource
    res = GATHER_ALIASES.get(low, low)
    if res in RESOURCE_ITEM:
        pred = _resource_pred(sim, ag, res, set())
        target = sim.world.find_nearest(ag.x, ag.y, pred, 60)
        if target is None:
            raise ActionFailed(f"no {res} found nearby")
        yield from walk_adjacent(sim, ag, *target)
        return f"arrived next to {res} at {target}"
    raise ActionFailed(f"unknown target '{t}' (use a person name, 'home', 'structure:<id>', a block type, a resource or 'x,y')")


def follow_agent(sim, ag, other, until_adjacent=True, ticks=600):
    spent = 0
    while spent < ticks:
        if not other.alive:
            raise ActionFailed(f"{other.name} is dead")
        if until_adjacent and manhattan(ag.pos, other.pos) <= 1:
            return
        if manhattan(ag.pos, other.pos) > 60:
            raise ActionFailed(f"{other.name} is too far away")
        goals = sim.world.adjacent_goals(other.x, other.y, ag.id, ag.has_boat)
        path = sim.world.find_path(ag.pos, goals, ag.id, ag.has_boat, max_nodes=6000) if goals else None
        if not path:
            spent += 5
            yield from wait(5)
            continue
        for step in path[:4]:
            if not sim.world.passable(step[0], step[1], ag.id, ag.has_boat):
                break
            ag.x, ag.y = step
            spent += 1
            yield
    if until_adjacent:
        raise ActionFailed(f"could not catch up with {other.name}")


def act_follow(sim, ag, p):
    other = sim.find_agent(p.get("target", ""))
    if other is None:
        raise ActionFailed("unknown person")
    ticks = min(2000, max(20, _int(p, "ticks", 300)))
    spent = 0
    while spent < ticks:
        if not other.alive:
            raise ActionFailed(f"{other.name} died")
        if manhattan(ag.pos, other.pos) > 2:
            yield from follow_agent(sim, ag, other, until_adjacent=True, ticks=40)
            spent += 40
        else:
            spent += 1
            yield
    return f"followed {other.name} for {ticks} ticks"


def act_explore(sim, ag, p):
    d = str(p.get("direction", "random")).lower()
    dist = min(60, max(5, _int(p, "distance", 25)))
    dirs = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
            "northeast": (1, -1), "northwest": (-1, -1), "southeast": (1, 1), "southwest": (-1, 1)}
    vx, vy = dirs.get(d, rng.choice(list(dirs.values())))
    tx = max(0, min(sim.world.w - 1, ag.x + vx * dist))
    ty = max(0, min(sim.world.h - 1, ag.y + vy * dist))
    target = sim.world.find_nearest(tx, ty, lambda a, b: sim.world.passable(a, b, ag.id, ag.has_boat), 15)
    if target is None:
        raise ActionFailed("nothing walkable in that direction")
    yield from walk_to(sim, ag, {target})
    sim.update_known(ag, radius=20)
    return f"explored to {ag.pos}"


def act_wait(sim, ag, p):
    n = min(600, max(1, _int(p, "ticks", 50)))
    yield from wait(n)
    return f"waited {n} ticks"


def act_set_home(sim, ag, p):
    ag.home = (_int(p, "x", ag.x), _int(p, "y", ag.y))
    return f"home set to {ag.home}"
    yield


# ============================================================== récolte
def _resource_pred(sim, ag, resource, bad):
    w = sim.world
    if resource == "sand":
        return lambda x, y: (x, y) not in bad and w.ground[y, x] == W.SAND and (x, y) not in w.blocks \
            and w.feature[y, x] == W.NONE
    feats = W.RESOURCE_FEATURES.get(resource)
    if feats is None:
        raise ActionFailed(f"unknown resource '{resource}'. Valid: {', '.join(I.GATHERABLE)}")

    def pred(x, y):
        return (x, y) not in bad and int(w.feature[y, x]) in feats and w.amount[y, x] > 0 \
            and w.has_free_neighbor(x, y, ag.id)
    return pred


GATHER_ALIASES = {"log": "wood", "logs": "wood", "tree": "wood", "trees": "wood", "cobblestone": "stone",
                  "rock": "stone", "iron_ore": "iron", "gold_ore": "gold", "berry": "berries",
                  "wheat_seeds": "seeds", "raw_mushroom": "mushroom", "grass": "fiber", "string": "fiber",
                  "coal_ore": "coal", "diamonds": "diamond", "gravel": "flint"}
RESOURCE_ITEM = {"wood": "log", "stone": "cobblestone", "coal": "coal", "iron": "iron_ore", "gold": "gold_ore",
                 "diamond": "diamond", "berries": "berries", "fiber": "fiber", "seeds": "wheat_seeds",
                 "sand": "sand", "clay": "clay", "mushroom": "raw_mushroom", "flint": "flint"}


def act_gather(sim, ag, p):
    resource = str(p.get("resource", "wood")).lower()
    resource = GATHER_ALIASES.get(resource, resource)
    amount = min(200, max(1, _int(p, "amount", 10)))
    item = RESOURCE_ITEM.get(resource)
    if item is None:
        raise ActionFailed(f"unknown resource '{resource}'. Valid: {', '.join(I.GATHERABLE)}")
    w = sim.world
    got = 0
    bad = set()
    start_count = ag.inv.get(item, 0)
    max_r = min(80, max(20, _int(p, "radius", 45)))
    while ag.inv.get(item, 0) - start_count < amount:
        pred = _resource_pred(sim, ag, resource, bad)
        target = w.find_nearest(ag.x, ag.y, pred, max_r)
        if target is None:
            if got == 0:
                raise ActionFailed(f"no {resource} found within {max_r} tiles")
            return f"gathered {ag.inv.get(item, 0) - start_count} {item} (no more {resource} nearby)"
        tx, ty = target
        try:
            yield from walk_adjacent(sim, ag, tx, ty)
        except ActionFailed:
            bad.add(target)
            if len(bad) > 12:
                raise ActionFailed(f"cannot reach any {resource}" + enclosed_hint(sim, ag))
            continue
        if manhattan(ag.pos, target) > 1:
            bad.add(target)
            continue
        # récolte sur cette case jusqu'à épuisement
        while ag.inv.get(item, 0) - start_count < amount:
            if resource == "sand":
                tier, tool = ag.best_tool("shovel")
                yield from wait(work_time(8, tier))
                ag.use_tool(tool)
                ag.add("sand")
                got += 1
                if rng.random() < 0.25:
                    break
                continue
            f = int(w.feature[ty, tx])
            if not w.has_resource(tx, ty, f) or f not in W.HARVEST:
                break
            kind, min_tier, base, product = W.HARVEST[f]
            tier, tool = ag.best_tool(kind) if kind else (0, None)
            if tier < min_tier:
                need = {1: "any pickaxe (wooden_pickaxe+)", 2: "stone_pickaxe or better", 3: "iron_pickaxe or better"}
                raise ActionFailed(f"{W.FEATURE_NAMES[f]} requires {need.get(min_tier, kind)}")
            yield from wait(work_time(base, tier))
            if not w.has_resource(tx, ty, f):
                break
            w.take_feature(tx, ty, sim.tick)
            ag.use_tool(tool)
            got += 1
            if f == W.TALL_GRASS:
                ag.add("fiber")
                if rng.random() < 0.35:
                    ag.add("wheat_seeds")
            else:
                ag.add(product)
            if f == W.TREE:
                if rng.random() < 0.06:
                    ag.add("apple")
                if rng.random() < 0.15:
                    ag.add("sapling")
                if rng.random() < 0.2:
                    ag.add("stick")
            if f == W.ROCK and rng.random() < 0.06:
                ag.add("flint")
    sim.update_known(ag, radius=10)
    return f"gathered {ag.inv.get(item, 0) - start_count} {item}"


# ============================================================== fabrication
STATION_OK = {
    None: lambda st: True,
    "crafting_table": lambda st: "crafting_table" in st,
    "furnace": lambda st: "furnace" in st,
    "anvil": lambda st: "anvil" in st,
    "cook": lambda st: "furnace" in st or "campfire" in st,
}


def _recipe_for(item, ag):
    if item in I.RECIPES:
        cands = [item]
    else:
        cands = [n for n in I.RECIPES if I.recipe_output_item(n) == item]
    if not cands:
        return None
    # choisit la variante dont on a les ingrédients
    for c in cands:
        if all(ag.inv.get(k, 0) >= v for k, v in I.RECIPES[c]["in"].items() if k != "fuel"):
            return c
    return cands[0]


def _fuel_available(ag, reserved):
    for f in I.FUEL_ITEMS:
        if ag.inv.get(f, 0) - reserved.get(f, 0) > 0:
            return f
    return None


def _can_craft_once(ag, recipe):
    r = I.RECIPES[recipe]
    reserved = dict(r["in"])
    for k, v in r["in"].items():
        if k == "fuel":
            continue
        if ag.inv.get(k, 0) < v:
            return False, k
    if "fuel" in r["in"]:
        if _fuel_available(ag, reserved) is None:
            return False, "fuel (coal/charcoal/log/planks/stick)"
    return True, None


def _do_craft_once(ag, recipe):
    r = I.RECIPES[recipe]
    reserved = dict(r["in"])
    fuel = _fuel_available(ag, reserved) if "fuel" in r["in"] else None
    for k, v in r["in"].items():
        if k == "fuel":
            continue
        ag.remove(k, v)
    if fuel:
        ag.remove(fuel, 1)
    ag.add(I.recipe_output_item(recipe), r["out"])


def _find_station(sim, ag, station):
    ok = STATION_OK[station]
    types = {"crafting_table": ["crafting_table"], "furnace": ["furnace"], "anvil": ["anvil"],
             "cook": ["campfire", "furnace"]}[station]
    best = None
    for (x, y), b in sim.world.blocks.items():
        if b.type in types:
            d = manhattan(ag.pos, (x, y))
            if d <= 50 and (best is None or d < best[0]):
                best = (d, x, y)
    return best, ok


def _ensure_station(sim, ag, station):
    if station is None:
        return
    ok = STATION_OK[station]
    if ok(sim.world.stations_near(ag.x, ag.y, 3)):
        return
    best, _ = _find_station(sim, ag, station)
    if best is None:
        name = "furnace or campfire" if station == "cook" else station
        raise ActionFailed(f"needs a {name} placed within 3 tiles; none known nearby (craft one and 'place' it)")
    yield from walk_within(sim, ag, best[1], best[2], 2)


def craft_item(sim, ag, item, count, depth=0):
    """Fabrique `count` exemplaires de `item`, en fabriquant automatiquement les
    ingrédients intermédiaires (planches, bâtons, ficelle...) si possible."""
    recipe = _recipe_for(item, ag)
    if recipe is None:
        raise ActionFailed(f"no recipe for '{item}'")
    r = I.RECIPES[recipe]
    out_item = I.recipe_output_item(recipe)
    target = ag.inv.get(out_item, 0) + count
    made = 0
    while ag.inv.get(out_item, 0) < target:
        ok, missing = _can_craft_once(ag, recipe)
        if not ok:
            if depth < 3 and missing in I.all_item_names() and _recipe_for(missing, ag) is not None \
                    and I.RECIPES[_recipe_for(missing, ag)]["station"] in (None, "crafting_table"):
                need = r["in"][missing] - ag.inv.get(missing, 0)
                before = ag.inv.get(missing, 0)
                try:
                    yield from craft_item(sim, ag, missing, need, depth + 1)
                except ActionFailed:
                    pass
                if ag.inv.get(missing, 0) > before:
                    continue
            if made == 0:
                ins = ", ".join(f"{v} {k}" for k, v in r["in"].items())
                raise ActionFailed(f"cannot craft {out_item}: missing {missing} (recipe needs {ins})")
            return made
        yield from _ensure_station(sim, ag, r["station"])
        yield from wait(15 if r["station"] in ("furnace", "cook") else 5)
        ok, missing = _can_craft_once(ag, recipe)
        if not ok:
            continue
        _do_craft_once(ag, recipe)
        made += r["out"]
    return made


def act_craft(sim, ag, p):
    item = norm_item(p.get("item", ""))
    count = min(64, max(1, _int(p, "count", 1)))
    made = yield from craft_item(sim, ag, item, count)
    return f"crafted {made} {item} (now have {ag.inv.get(item, 0)})"


# ============================================================== nourriture
def act_eat(sim, ag, p):
    item = norm_item(p.get("item", "best"))
    count = min(10, max(1, _int(p, "count", 1)))
    eaten = 0
    for _ in range(count):
        if ag.hunger >= 100:
            break
        it = item
        if it in ("best", "auto", "any", "food"):
            foods = ag.food_items()
            if not foods:
                break
            it = foods[0][1]
        if it not in I.FOOD:
            raise ActionFailed(f"'{it}' is not edible")
        if not ag.remove(it, 1):
            break
        sim.feed(ag, it)
        eaten += 1
        yield from wait(4)
    if eaten == 0:
        raise ActionFailed("nothing to eat")
    return f"ate {eaten} (hunger now {ag.hunger:.0f})"


# ============================================================== construction
def act_build(sim, ag, p):
    try:
        kind, x, y, w, h, cells, note = BP.relocate(sim.world, p, ag.id)
    except BP.BlueprintError as e:
        raise ActionFailed(str(e))
    label = str(p.get("name", p.get("label", kind)))[:40]
    site = sim.new_site(ag, kind, x, y, w, h, label, cells)
    res = yield from run_site(sim, ag, site)
    return res + note


def act_continue_build(sim, ag, p):
    sid = _int(p, "site_id", _int(p, "id", -1))
    site = sim.structures.get(sid)
    if site is None:
        raise ActionFailed(f"unknown site #{sid}")
    if site.status == "complete":
        return f"site #{sid} already complete"
    return (yield from run_site(sim, ag, site))


def _clear_tile_for_build(sim, ag, x, y):
    """Coupe l'arbre / casse la roche sur une case à construire. Renvoie False si impossible."""
    w = sim.world
    f = int(w.feature[y, x])
    if f in (W.TREE,) or f in W.SOLID_FEATURES:
        kind, min_tier, base, product = W.HARVEST[f]
        tier, tool = ag.best_tool(kind)
        if tier < min_tier:
            return False
        while w.feature[y, x] == f and w.amount[y, x] > 0:
            yield from wait(work_time(base, tier))
            w.take_feature(x, y, sim.tick)
            ag.use_tool(tool)
            ag.add(product)
        if w.feature[y, x] == W.SAPLING:
            w.feature[y, x] = W.NONE
            w._update_cell(x, y)
            w.regrow = [r for r in w.regrow if (r[1], r[2]) != (x, y)]
            import heapq
            heapq.heapify(w.regrow)
    return True


def run_site(sim, ag, site):
    w = sim.world
    site.status = "in_progress"
    skipped = []
    i = site.done
    while i < len(site.cells):
        x, y, op, mat = site.cells[i]
        # déjà fait ?
        if op == "block":
            b = w.blocks.get((x, y))
            if b is not None and b.type == mat:
                i += 1
                site.done = i
                continue
        elif op == "roof" and w.roofs.get((x, y)) == mat:
            i += 1
            site.done = i
            continue
        elif op == "till" and w.ground[y, x] == W.FARMLAND:
            i += 1
            site.done = i
            continue
        elif op == "plant" and (x, y) in w.crops:
            i += 1
            site.done = i
            continue

        # matériaux
        if op in ("block", "roof"):
            if ag.inv.get(mat, 0) <= 0:
                # tentative de fabrication automatique simple (planches depuis bûches, etc.)
                rec = _recipe_for(mat, ag)
                if rec and I.RECIPES[rec]["station"] in (None, "crafting_table") and mat not in ("log", "cobblestone"):
                    try:
                        yield from craft_item(sim, ag, mat, 1)
                    except ActionFailed:
                        pass
            if ag.inv.get(mat, 0) <= 0:
                site.status = "paused"
                site.missing = site.needs()
                need = ", ".join(f"{v} {k}" for k, v in site.missing.items())
                raise ActionFailed(f"site #{site.id} paused at {site.done}/{len(site.cells)}: out of {mat}. "
                                   f"Still needs: {need}. Use continue_build site_id={site.id} when you have them")
        if op == "till":
            tier, hoe = ag.best_tool("hoe")
            if hoe is None:
                site.status = "paused"
                raise ActionFailed(f"site #{site.id}: tilling farmland needs a hoe")
        if op == "plant" and ag.inv.get("wheat_seeds", 0) <= 0:
            site.status = "paused"
            site.missing = site.needs()
            raise ActionFailed(f"site #{site.id} paused: out of wheat_seeds "
                               f"({len(site.cells) - site.done} cells left). continue_build site_id={site.id} later")

        # aller sur place
        try:
            if op == "roof":
                yield from walk_within(sim, ag, x, y, 2)
            else:
                yield from walk_adjacent(sim, ag, x, y)
        except ActionFailed:
            skipped.append((x, y))
            site.cells.append(site.cells.pop(i)) if len(skipped) < 30 else None
            if len(skipped) >= 30:
                break
            continue

        if op == "block":
            b = w.blocks.get((x, y))
            if b is not None and b.type != mat:
                skipped.append((x, y))
                i += 1
                site.done = i
                continue
            if not (yield from _clear_tile_for_build(sim, ag, x, y)):
                skipped.append((x, y))
                i += 1
                site.done = i
                continue
            # attendre qu'un occupant libère la case
            for _ in range(20):
                if ag.pos != (x, y) and not sim.occupied(x, y):
                    break
                if ag.pos == (x, y):
                    nb = [n for n in w.adjacent_goals(x, y, ag.id) if n != (x, y)]
                    if nb:
                        ag.x, ag.y = nb[0]
                yield
            if ag.pos == (x, y) or sim.occupied(x, y) or w.ground[y, x] == W.WATER:
                skipped.append((x, y))
                i += 1
                site.done = i
                continue
            yield from wait(4)
            ag.remove(mat, 1)
            w.place_block(x, y, mat, ag.id, site.id)
        elif op == "roof":
            yield from wait(3)
            ag.remove(mat, 1)
            w.roofs[(x, y)] = mat
            w.version += 1
        elif op == "till":
            if w.ground[y, x] not in (W.GRASS, W.DIRT) or (x, y) in w.blocks:
                skipped.append((x, y))
                i += 1
                site.done = i
                continue
            if w.feature[y, x] == W.TREE:
                yield from _clear_tile_for_build(sim, ag, x, y)
            yield from wait(work_time(10, ag.best_tool("hoe")[0]))
            if w.feature[y, x] == W.TALL_GRASS and rng.random() < 0.3:
                ag.add("wheat_seeds")
            w.feature[y, x] = W.NONE
            w.amount[y, x] = 0
            w.ground[y, x] = W.FARMLAND
            w._update_cell(x, y)
            ag.use_tool(ag.best_tool("hoe")[1])
            w.version += 1
        elif op == "plant":
            if w.ground[y, x] != W.FARMLAND:
                skipped.append((x, y))
                i += 1
                site.done = i
                continue
            yield from wait(2)
            ag.remove("wheat_seeds", 1)
            w.crops[(x, y)] = {"stage": 0, "growth": 0, "owner": ag.id}
            w.version += 1
        i += 1
        site.done = i

    site.status = "complete"
    site.missing = {}
    sim.event(f"{ag.name} a terminé {site.kind} #{site.id} '{site.label}' en ({site.x},{site.y})", ag.pos, [ag])
    extra = f" ({len(skipped)} cells skipped: blocked)" if skipped else ""
    return f"site #{site.id} {site.kind} complete{extra}"


def act_place(sim, ag, p):
    block = str(p.get("block", p.get("item", ""))).lower()
    if block not in I.BLOCKS:
        raise ActionFailed(f"'{block}' is not a placeable block")
    if ag.inv.get(block, 0) <= 0:
        rec = _recipe_for(block, ag)
        if rec:
            yield from craft_item(sim, ag, block, 1)
        if ag.inv.get(block, 0) <= 0:
            raise ActionFailed(f"you have no {block}")
    x, y = _int(p, "x", ag.x), _int(p, "y", ag.y)
    w = sim.world
    if not w.buildable(x, y) or (x, y) == ag.pos:
        cand = w.find_nearest(x, y, lambda a, b: w.buildable(a, b) and (a, b) != ag.pos
                              and not sim.occupied(a, b) and w.has_free_neighbor(a, b, ag.id), 5)
        if cand is None:
            raise ActionFailed(f"cannot place at ({x},{y})")
        x, y = cand
    yield from walk_adjacent(sim, ag, x, y)
    if ag.pos == (x, y):
        nb = [n for n in w.adjacent_goals(x, y, ag.id)]
        if not nb:
            raise ActionFailed("no room to step aside")
        ag.x, ag.y = nb[0]
    yield from wait(4)
    if not w.buildable(x, y):
        raise ActionFailed(f"({x},{y}) became occupied")
    ag.remove(block, 1)
    w.place_block(x, y, block, ag.id)
    if block == "bed" and ag.home is None:
        ag.home = (x, y)
    if block == "sign":
        w.blocks[(x, y)].text = str(p.get("text", ""))[:80]
    return f"placed {block} at ({x},{y})"


def act_write_sign(sim, ag, p):
    x, y = _int(p, "x", ag.x), _int(p, "y", ag.y)
    b = sim.world.blocks.get((x, y))
    if b is None or b.type != "sign":
        q = dict(p, block="sign")
        res = yield from act_place(sim, ag, q)
        return res
    yield from walk_adjacent(sim, ag, x, y)
    b.text = str(p.get("text", ""))[:80]
    return f"wrote on sign at ({x},{y})"


def act_demolish(sim, ag, p):
    w = sim.world
    x, y = _int(p, "x", ag.x), _int(p, "y", ag.y)
    ww, hh = min(16, max(1, _int(p, "w", 1))), min(16, max(1, _int(p, "h", 1)))
    sid = p.get("site_id")
    targets = []
    if sid is not None:
        s = sim.structures.get(_int(p, "site_id", -1))
        if not s:
            raise ActionFailed("unknown site")
        targets = [(cx, cy) for (cx, cy, op, _) in s.cells if op == "block" and (cx, cy) in w.blocks]
        roofs = [(cx, cy) for (cx, cy, op, _) in s.cells if op == "roof" and (cx, cy) in w.roofs]
    else:
        targets = [(x + dx, y + dy) for dy in range(hh) for dx in range(ww) if (x + dx, y + dy) in w.blocks]
        roofs = [(x + dx, y + dy) for dy in range(hh) for dx in range(ww) if (x + dx, y + dy) in w.roofs]
    if not targets and not roofs:
        raise ActionFailed("nothing to demolish there")
    broken = 0
    for (cx, cy) in roofs:
        yield from walk_within(sim, ag, cx, cy, 2)
        yield from wait(3)
        mat = w.roofs.pop((cx, cy), None)
        if mat:
            ag.add(mat)
            w.version += 1
    for (cx, cy) in targets:
        b = w.blocks.get((cx, cy))
        if b is None:
            continue
        yield from walk_adjacent(sim, ag, cx, cy)
        stoney = b.type in ("cobblestone", "brick", "furnace", "anvil", "iron_block", "iron_door", "glass")
        tier, tool = ag.best_tool("pickaxe" if stoney else "axe")
        _, wdmg = ag.weapon()
        per_hit = 1 + tier * 2 + (wdmg / 3)
        while (cx, cy) in w.blocks and w.blocks[(cx, cy)] is b:
            yield from wait(6)
            b.hp -= per_hit
            if b.hp <= 0:
                w.remove_block(cx, cy)
                ag.add(b.type)
                ag.use_tool(tool)
                broken += 1
                if b.owner is not None and b.owner != ag.id:
                    owner = sim.agents.get(b.owner)
                    sim.witness(ag.pos, f"{ag.name} a détruit un(e) {b.type} appartenant à "
                                f"{owner.name if owner else '?'} en ({cx},{cy})", exclude={ag.id})
                    if owner and owner.alive:
                        near = manhattan(owner.pos, ag.pos) <= sim.cfg.witness_radius
                        who = ag.name if near else "quelqu'un"
                        sim.remember(owner, f"Ton {b.type} en ({cx},{cy}) a été détruit par {who}.")
                        sim.wake(owner, f"your {b.type} at ({cx},{cy}) was destroyed by {who}")
    return f"demolished {broken} blocks and {len(roofs)} roof tiles (materials recovered)"


# ============================================================== agriculture
def act_harvest(sim, ag, p):
    w = sim.world
    radius = min(30, max(3, _int(p, "radius", 15)))
    cx, cy = _int(p, "x", ag.x), _int(p, "y", ag.y)
    replant = p.get("replant", True) not in (False, "no", "false")
    n = 0
    max_n = min(200, max(1, _int(p, "amount", 100)))
    while n < max_n:
        ripe = [pos for pos, c in w.crops.items() if c["stage"] >= 3 and cheb(pos, (cx, cy)) <= radius]
        if not ripe:
            break
        ripe.sort(key=lambda q: manhattan(q, ag.pos))
        x, y = ripe[0]
        yield from walk_adjacent(sim, ag, x, y)
        yield from wait(3)
        c = w.crops.get((x, y))
        if not c or c["stage"] < 3:
            continue
        owner = c.get("owner")
        del w.crops[(x, y)]
        ag.add("wheat", rng.randint(1, 2))
        ag.add("wheat_seeds", rng.randint(1, 2))
        n += 1
        if owner is not None and owner != ag.id:
            o = sim.agents.get(owner)
            if o is not None and o.alive and manhattan(o.pos, ag.pos) <= sim.cfg.witness_radius:
                sim.remember(o, f"{ag.name} a récolté ton blé en ({x},{y}).")
        if replant and ag.remove("wheat_seeds", 1):
            w.crops[(x, y)] = {"stage": 0, "growth": 0, "owner": ag.id}
        w.version += 1
    if n == 0:
        raise ActionFailed("no ripe crops in range")
    return f"harvested {n} wheat plants"


def act_plant(sim, ag, p):
    w = sim.world
    item = str(p.get("item", "wheat_seeds")).lower()
    count = min(50, max(1, _int(p, "count", 5)))
    cx, cy = _int(p, "x", ag.x), _int(p, "y", ag.y)
    planted = 0
    for _ in range(count):
        if ag.inv.get(item, 0) <= 0:
            break
        if item == "wheat_seeds":
            pred = lambda a, b: w.ground[b, a] == W.FARMLAND and (a, b) not in w.crops and (a, b) not in w.blocks
        elif item == "sapling":
            pred = lambda a, b: w.ground[b, a] in (W.GRASS, W.DIRT) and w.feature[b, a] == W.NONE \
                and (a, b) not in w.blocks and not sim.occupied(a, b)
        else:
            raise ActionFailed("you can plant wheat_seeds (on farmland) or sapling")
        t = w.find_nearest(cx, cy, pred, 12)
        if t is None:
            if planted == 0:
                raise ActionFailed("no free farmland nearby (build a farm first)" if item == "wheat_seeds"
                                   else "no free ground nearby")
            break
        yield from walk_adjacent(sim, ag, *t)
        yield from wait(3)
        ag.remove(item, 1)
        if item == "wheat_seeds":
            w.crops[t] = {"stage": 0, "growth": 0, "owner": ag.id}
        else:
            import heapq
            w.feature[t[1], t[0]] = W.SAPLING
            w.amount[t[1], t[0]] = 1
            w._update_cell(*t)
            heapq.heappush(w.regrow, (sim.tick + rng.randint(2000, 3500), t[0], t[1], W.TREE, 4))
        w.version += 1
        planted += 1
    return f"planted {planted} {item}"


# ============================================================== animaux
def _find_animal(sim, ag, spec, radius=35, pred=None):
    """spec : espèce ('sheep') ou id ('#12' / 12)."""
    s = str(spec).lower().lstrip("#")
    if s.isdigit():
        a = sim.animals.animals.get(int(s))
        return a if a and a.alive else None
    best = None
    for a in sim.animals.near(ag.x, ag.y, radius, s):
        if pred and not pred(a):
            continue
        d = manhattan(a.pos, ag.pos)
        if best is None or d < best[0]:
            best = (d, a)
    return best[1] if best else None


def chase(sim, ag, target, reach=1, max_ticks=400):
    """Rapproche l'agent d'une cible mobile."""
    spent = 0
    while manhattan(ag.pos, target.pos) > reach:
        if not target.alive:
            return False
        if spent > max_ticks or manhattan(ag.pos, target.pos) > 40:
            return False
        goals = sim.world.adjacent_goals(target.x, target.y, ag.id, ag.has_boat)
        if reach > 1:
            goals |= {(target.x + dx, target.y + dy) for dx in range(-reach, reach + 1)
                      for dy in range(-reach, reach + 1) if abs(dx) + abs(dy) <= reach
                      and sim.world.passable(target.x + dx, target.y + dy, ag.id, ag.has_boat)}
        path = sim.world.find_path(ag.pos, goals, ag.id, ag.has_boat, max_nodes=5000) if goals else None
        if not path:
            spent += 4
            yield from wait(4)
            continue
        for step in path[:3]:
            if not sim.world.passable(step[0], step[1], ag.id, ag.has_boat):
                break
            ag.x, ag.y = step
            spent += 1
            yield
    return True


def strike(sim, ag, target):
    """Un coup (mêlée ou à distance). Renvoie True si la cible meurt."""
    d = manhattan(ag.pos, target.pos)
    rd = ag.ranged()
    if rd and 1 < d <= rd[2]:
        item, dmg, _rng, ammo = rd
        ag.remove(ammo, 1)
        if rng.random() < 0.25:
            return False  # raté
    else:
        weapon, dmg = ag.weapon()
        ag.use_tool(weapon)
    if isinstance(target, Animal):
        dead = sim.animals.damage(target, dmg, ag.pos, attacker=ag)
        if dead:
            drops = sim.animals.kill(target, ag)
            for k, v in drops.items():
                ag.add(k, v)
        return dead
    return sim.damage_agent(target, dmg, attacker=ag)


def act_hunt(sim, ag, p):
    species = str(p.get("animal", "")).lower()
    if species not in I.ANIMALS and not species.lstrip("#").isdigit():
        raise ActionFailed(f"unknown animal '{species}'. Animals: {', '.join(I.ANIMALS)}")
    count = min(20, max(1, _int(p, "count", 1)))
    killed = 0
    failed = set()
    attempts = 0
    while killed < count and attempts < count + 6:
        attempts += 1
        a = _find_animal(sim, ag, species, pred=lambda a: a.owner is None and a.id not in failed)
        if a is None:
            break
        ag.combat_target = a
        while a.alive:
            reach = ag.ranged()[2] if ag.ranged() else 1
            ok = yield from chase(sim, ag, a, reach=reach)
            if not ok:
                failed.add(a.id)
                yield
                break
            if ag.attack_cd > 0:
                yield
                continue
            ag.attack_cd = 8
            if strike(sim, ag, a):
                killed += 1
                break
            yield
        ag.combat_target = None
        if species.lstrip("#").isdigit():
            break
    if killed == 0:
        raise ActionFailed(f"could not hunt any {species}")
    return f"killed {killed} {species}"


def act_attack(sim, ag, p):
    tname = str(p.get("target", ""))
    flee_hp = max(0, min(19, _int(p, "flee_below_hp", 5)))
    target = sim.find_agent(tname)
    if target is None:
        a = _find_animal(sim, ag, tname)
        if a is None:
            raise ActionFailed(f"no target '{tname}'")
        return (yield from act_hunt(sim, ag, {"animal": f"#{a.id}"}))
    if target.id == ag.id:
        raise ActionFailed("cannot attack yourself")
    ag.combat_target = target
    sim.on_aggression(ag, target)
    hits = 0
    try:
        while target.alive:
            if ag.hp < flee_hp:
                yield from _flee(sim, ag, target.pos, 15)
                raise ActionFailed(f"retreated from {target.name} with low HP ({ag.hp:.0f})")
            reach = ag.ranged()[2] if ag.ranged() else 1
            ok = yield from chase(sim, ag, target, reach=reach, max_ticks=300)
            if not ok:
                if not target.alive:
                    break
                raise ActionFailed(f"{target.name} escaped")
            if ag.attack_cd > 0:
                yield
                continue
            ag.attack_cd = 10
            hits += 1
            if strike(sim, ag, target):
                break
            yield
    finally:
        ag.combat_target = None
    return f"{target.name} is dead after {hits} hits"


def _flee(sim, ag, from_pos, dist):
    w = sim.world
    vx, vy = ag.x - from_pos[0], ag.y - from_pos[1]
    n = math.hypot(vx, vy) or 1
    tx = int(max(0, min(w.w - 1, ag.x + vx / n * dist)))
    ty = int(max(0, min(w.h - 1, ag.y + vy / n * dist)))
    t = w.find_nearest(tx, ty, lambda a, b: w.passable(a, b, ag.id, ag.has_boat), 10)
    if t:
        try:
            yield from walk_to(sim, ag, {t}, max_ticks=200)
        except ActionFailed:
            pass


def act_flee(sim, ag, p):
    t = sim.find_agent(p.get("from", p.get("target", "")))
    pos = t.pos if t else (_int(p, "x", ag.x - 1), _int(p, "y", ag.y))
    yield from _flee(sim, ag, pos, min(40, max(5, _int(p, "distance", 20))))
    return f"fled to {ag.pos}"


def act_lead(sim, ag, p):
    species = str(p.get("animal", ""))
    if ag.inv.get("rope_lead", 0) <= 0:
        try:
            yield from craft_item(sim, ag, "rope_lead", 1)
        except ActionFailed:
            raise ActionFailed("you need a rope_lead (2 string; string = 3 fiber)")
    a = _find_animal(sim, ag, species, pred=lambda a: a.leashed_to is None and a.species != "wolf")
    if a is None:
        raise ActionFailed(f"no {species} to leash nearby")
    ok = yield from chase(sim, ag, a, reach=1)
    if not ok:
        raise ActionFailed(f"could not reach the {a.species}")
    ag.remove("rope_lead", 1)
    a.leashed_to = ag.id
    a.flee_ticks = 0
    if "x" in p and "y" in p:
        tx, ty = _int(p, "x"), _int(p, "y")
        yield from walk_within(sim, ag, tx, ty, 1)
        yield from wait(6)
        # relâche l'animal sur la case cible si possible
        if sim.world.passable(tx, ty, ag.id) and not sim.world.blocks.get((tx, ty)):
            a.x, a.y = tx, ty
        a.leashed_to = None
        ag.add("rope_lead", 1)
        return f"led {a.species} #{a.id} to ({a.x},{a.y}) and released it"
    return f"{a.species} #{a.id} is now on your leash (it follows you; use release)"


def act_release(sim, ag, p):
    n = 0
    for a in list(sim.animals.animals.values()):
        if a.leashed_to == ag.id and (p.get("animal") in (None, "all", a.species) or str(a.id) == str(p.get("animal")).lstrip("#")):
            a.leashed_to = None
            ag.add("rope_lead", 1)
            n += 1
    yield
    return f"released {n} animals"


BREED_FOOD = {"cow": "wheat", "sheep": "wheat", "chicken": "wheat_seeds", "pig": "berries", "wolf": "raw_beef"}


def act_breed(sim, ag, p):
    species = str(p.get("animal", "")).lower()
    food = BREED_FOOD.get(species)
    if food is None:
        raise ActionFailed(f"cannot breed '{species}'")
    if ag.inv.get(food, 0) < 2:
        raise ActionFailed(f"breeding {species} needs 2 {food}")
    cands = [a for a in sim.animals.near(ag.x, ag.y, 8, species) if a.adult and a.breed_cooldown == 0]
    if len(cands) < 2:
        raise ActionFailed(f"need 2 adult {species} (not recently bred) within 8 tiles")
    a, b = cands[0], cands[1]
    ok = yield from chase(sim, ag, a, 1)
    if not ok:
        raise ActionFailed("animal unreachable")
    ok = yield from chase(sim, ag, b, 1)
    if not ok:
        raise ActionFailed("animal unreachable")
    yield from wait(10)
    ag.remove(food, 2)
    a.breed_cooldown = b.breed_cooldown = 1500
    baby = sim.animals.spawn(species, a.x, a.y, age=0)
    baby.owner = ag.id if species == "wolf" else None
    return f"a baby {species} #{baby.id} was born"


def act_shear(sim, ag, p):
    if ag.inv.get("shears", 0) <= 0:
        raise ActionFailed("you need shears (2 iron_ingot)")
    count = min(10, max(1, _int(p, "count", 3)))
    n = 0
    sheared = getattr(sim, "_sheared", {})
    sim._sheared = sheared
    for _ in range(count):
        a = _find_animal(sim, ag, "sheep", pred=lambda a: sheared.get(a.id, 0) <= sim.tick and a.adult)
        if a is None:
            break
        ok = yield from chase(sim, ag, a, 1)
        if not ok:
            break
        yield from wait(5)
        ag.add("wool", rng.randint(1, 3))
        ag.use_tool("shears")
        sheared[a.id] = sim.tick + 2000
        n += 1
    if n == 0:
        raise ActionFailed("no unsheared adult sheep nearby")
    return f"sheared {n} sheep"


def act_tame(sim, ag, p):
    if ag.inv.get("bone", 0) <= 0:
        raise ActionFailed("taming a wolf needs bones")
    a = _find_animal(sim, ag, "wolf", pred=lambda a: a.owner is None)
    if a is None:
        raise ActionFailed("no wild wolf nearby")
    while ag.inv.get("bone", 0) > 0 and a.alive:
        ok = yield from chase(sim, ag, a, 1)
        if not ok:
            raise ActionFailed("wolf unreachable")
        yield from wait(5)
        ag.remove("bone", 1)
        if rng.random() < 0.34:
            a.owner = ag.id
            a.target = None
            return f"tamed wolf #{a.id}; it follows and protects you"
    raise ActionFailed("ran out of bones, the wolf is still wild")


def act_fish(sim, ag, p):
    if ag.inv.get("fishing_rod", 0) <= 0:
        raise ActionFailed("you need a fishing_rod")
    w = sim.world
    count = min(20, max(1, _int(p, "count", 3)))
    t = w.find_nearest(ag.x, ag.y, lambda a, b: w.passable(a, b, ag.id) and any(
        w.in_bounds(nx, ny) and w.ground[ny, nx] == W.WATER for nx, ny in w.neighbors4(a, b)), 40)
    if t is None:
        raise ActionFailed("no shore nearby")
    yield from walk_to(sim, ag, {t})
    for _ in range(count):
        yield from wait(rng.randint(30, 110))
        ag.add("raw_fish")
        ag.use_tool("fishing_rod")
        if ag.inv.get("fishing_rod", 0) <= 0:
            break
    return f"caught fish (now {ag.inv.get('raw_fish', 0)} raw_fish)"


# ============================================================== social / échanges
def act_say(sim, ag, p):
    text = str(p.get("text", p.get("message", "")))[:300]
    to = p.get("to")
    if not text:
        raise ActionFailed("empty message")
    target = sim.find_agent(to) if to else None
    if to and target is None:
        raise ActionFailed(f"unknown person '{to}'")
    if target and manhattan(target.pos, ag.pos) > sim.cfg.hearing_radius:
        yield from follow_agent(sim, ag, target, until_adjacent=True, ticks=400)
    sim.speak(ag, text, target)
    yield from wait(5)
    return f"said: {text}"


def act_give(sim, ag, p):
    target = sim.find_agent(p.get("to", p.get("target", "")))
    if target is None:
        raise ActionFailed("unknown recipient")
    goods = _count_dict(p.get("items")) or {norm_item(p.get("item", "")): max(1, _int(p, "count", 1))}
    for k, v in goods.items():
        if ag.inv.get(k, 0) < v:
            raise ActionFailed(f"you only have {ag.inv.get(k, 0)} {k}")
    if manhattan(ag.pos, target.pos) > 2:
        yield from follow_agent(sim, ag, target)
    for k, v in goods.items():
        ag.remove(k, v)
        target.add(k, v)
    txt = ", ".join(f"{v} {k}" for k, v in goods.items())
    sim.remember(target, f"{ag.name} t'a donné {txt}.")
    sim.wake(target, f"{ag.name} gave you {txt}", soft=True)
    sim.event(f"{ag.name} donne {txt} à {target.name}", ag.pos, [ag, target])
    yield
    return f"gave {txt} to {target.name}"


def act_offer_trade(sim, ag, p):
    target = sim.find_agent(p.get("to", ""))
    if target is None:
        raise ActionFailed("unknown person")
    give = _count_dict(p.get("give"))
    want = _count_dict(p.get("want"))
    if not give and not want:
        raise ActionFailed("trade needs 'give' and/or 'want'")
    for k, v in give.items():
        if ag.inv.get(k, 0) < v:
            raise ActionFailed(f"you don't have {v} {k}")
    offer = sim.create_offer(ag, target, give, want)
    yield
    return f"offer #{offer['id']} sent to {target.name}"


def act_accept_trade(sim, ag, p):
    oid = _int(p, "offer_id", _int(p, "id", -1))
    offer = sim.trades.get(oid)
    if offer is None or offer["to"] != ag.id:
        raise ActionFailed(f"no pending offer #{oid} for you")
    other = sim.agents.get(offer["from"])
    if other is None or not other.alive:
        sim.trades.pop(oid, None)
        raise ActionFailed("the other person is gone")
    if manhattan(ag.pos, other.pos) > 6:
        yield from follow_agent(sim, ag, other)
    for k, v in offer["give"].items():
        if other.inv.get(k, 0) < v:
            sim.trades.pop(oid, None)
            raise ActionFailed(f"{other.name} no longer has {v} {k}")
    for k, v in offer["want"].items():
        if ag.inv.get(k, 0) < v:
            raise ActionFailed(f"you don't have {v} {k}")
    for k, v in offer["give"].items():
        other.remove(k, v)
        ag.add(k, v)
    for k, v in offer["want"].items():
        ag.remove(k, v)
        other.add(k, v)
    sim.trades.pop(oid, None)
    sim.remember(other, f"{ag.name} a accepté ton échange #{oid}.")
    sim.wake(other, f"{ag.name} accepted your trade #{oid}", soft=True)
    sim.event(f"Échange #{oid} entre {other.name} et {ag.name}", ag.pos, [ag, other])
    yield
    return f"trade #{oid} done"


def act_decline_trade(sim, ag, p):
    oid = _int(p, "offer_id", _int(p, "id", -1))
    offer = sim.trades.pop(oid, None)
    if offer is None:
        raise ActionFailed("no such offer")
    other = sim.agents.get(offer["from"])
    if other:
        sim.remember(other, f"{ag.name} a refusé ton échange #{oid}.")
    yield
    return f"declined trade #{oid}"


def _chest_at(sim, ag, p, own_only=False):
    w = sim.world
    if "x" in p and "y" in p:
        pos = (_int(p, "x"), _int(p, "y"))
        b = w.blocks.get(pos)
        if b is None or b.type != "chest":
            raise ActionFailed(f"no chest at {pos}")
        return pos, b
    best = None
    for pos, b in w.blocks.items():
        if b.type == "chest" and (not own_only or b.owner == ag.id):
            d = manhattan(pos, ag.pos)
            if best is None or d < best[0]:
                best = (d, pos, b)
    if best is None or best[0] > 60:
        raise ActionFailed("no chest nearby")
    return best[1], best[2]


def act_store(sim, ag, p):
    pos, chest = _chest_at(sim, ag, p, own_only=True)
    yield from walk_adjacent(sim, ag, *pos)
    goods = p.get("items", "all")
    if goods == "all":
        keep = set(I.MELEE_DAMAGE) | set(I.ARMOR) | set(I.RANGED) | {"arrow", "rope_lead", "boat"}
        for t in I.TOOLS.values():
            keep |= set(t)
        goods = {k: v for k, v in ag.inv.items() if k not in keep and k not in I.FOOD}
    else:
        goods = _count_dict(goods)
    moved = []
    for k, v in goods.items():
        v = min(v, ag.inv.get(k, 0))
        if v > 0:
            ag.remove(k, v)
            chest.inv[k] += v
            moved.append(f"{v} {k}")
    yield from wait(3)
    return f"stored {', '.join(moved) or 'nothing'} in chest at {pos}"


def act_take(sim, ag, p):
    pos, chest = _chest_at(sim, ag, p)
    yield from walk_adjacent(sim, ag, *pos)
    goods = p.get("items", "all")
    goods = dict(chest.inv) if goods == "all" else _count_dict(goods)
    taken = []
    for k, v in goods.items():
        v = min(v, chest.inv.get(k, 0))
        if v > 0:
            chest.inv[k] -= v
            if chest.inv[k] <= 0:
                del chest.inv[k]
            ag.add(k, v)
            taken.append(f"{v} {k}")
    if chest.owner is not None and chest.owner != ag.id and taken:
        owner = sim.agents.get(chest.owner)
        sim.witness(ag.pos, f"{ag.name} a pris {', '.join(taken)} dans le coffre de "
                    f"{owner.name if owner else '?'}", exclude={ag.id})
        if owner and owner.alive and manhattan(owner.pos, ag.pos) <= sim.cfg.witness_radius:
            sim.wake(owner, f"{ag.name} took items from your chest")
    yield from wait(3)
    return f"took {', '.join(taken) or 'nothing'} from chest at {pos}"


def act_pick_up(sim, ag, p):
    w = sim.world
    radius = min(20, max(1, _int(p, "radius", 8)))
    got = []
    for _ in range(20):
        piles = [pos for pos in w.ground_items if cheb(pos, ag.pos) <= radius]
        if not piles:
            break
        piles.sort(key=lambda q: manhattan(q, ag.pos))
        pos = piles[0]
        try:
            if w.passable(*pos, ag.id):
                yield from walk_to(sim, ag, {pos})
            else:
                yield from walk_adjacent(sim, ag, *pos)
        except ActionFailed:
            break
        items = w.pick_items(*pos)
        for k, v in items.items():
            ag.add(k, v)
            got.append(f"{v} {k}")
    if not got:
        raise ActionFailed("no items on the ground nearby")
    return f"picked up {', '.join(got)}"


def act_drop(sim, ag, p):
    item = norm_item(p.get("item", ""))
    n = min(ag.inv.get(item, 0), max(1, _int(p, "count", 1)))
    if n <= 0:
        raise ActionFailed(f"no {item} to drop")
    ag.remove(item, n)
    sim.world.drop_items(ag.x, ag.y, {item: n})
    yield
    return f"dropped {n} {item}"


def act_sleep(sim, ag, p):
    w = sim.world
    if not sim.is_night():
        raise ActionFailed("you can only sleep at night")
    bed = None
    best = None
    for pos, b in w.blocks.items():
        if b.type == "bed" and (b.owner == ag.id or b.owner is None):
            d = manhattan(pos, ag.pos)
            if d < 40 and (best is None or d < best):
                best, bed = d, pos
    if bed:
        try:
            yield from walk_to(sim, ag, {bed})
        except ActionFailed:
            bed = None
    ag.sleeping = True
    try:
        while sim.is_night():
            if bed:
                ag.hp = min(sim.cfg.max_hp, ag.hp + 0.03)
            yield
    finally:
        ag.sleeping = False
    return "slept until morning" + (" in a bed" if bed else " on the ground")


def act_allow(sim, ag, p):
    x, y = _int(p, "x"), _int(p, "y")
    b = sim.world.blocks.get((x, y))
    if b is None or b.owner != ag.id or b.type != "iron_door":
        raise ActionFailed("no iron_door of yours there")
    other = sim.find_agent(p.get("target", p.get("to", "")))
    if other is None:
        raise ActionFailed("unknown person")
    if p.get("revoke"):
        b.allowed.discard(other.id)
    else:
        b.allowed.add(other.id)
    yield
    return f"door access updated for {other.name}"


def act_propose_child(sim, ag, p):
    partner = sim.find_agent(p.get("partner", p.get("to", "")))
    if partner is None or partner.id == ag.id:
        raise ActionFailed("unknown partner")
    if manhattan(ag.pos, partner.pos) > 2:
        yield from follow_agent(sim, ag, partner)
    ag.child_proposal = (partner.id, sim.tick)
    if partner.child_proposal and partner.child_proposal[0] == ag.id and sim.tick - partner.child_proposal[1] < 600:
        res = sim.try_birth(ag, partner)
        if isinstance(res, str):
            raise ActionFailed(res)
        return f"a child named {res.name} was born!"
    sim.remember(partner, f"{ag.name} te propose d'avoir un enfant ensemble (il faut que tu fasses propose_child "
                          f"avec {ag.name} près de lui/elle).")
    sim.wake(partner, f"{ag.name} proposes to have a child with you")
    # attend la réponse
    for _ in range(300):
        yield
        if partner.child_proposal and partner.child_proposal[0] == ag.id and sim.tick - partner.child_proposal[1] < 600:
            if manhattan(ag.pos, partner.pos) > 2:
                continue
            res = sim.try_birth(ag, partner)
            if isinstance(res, str):
                raise ActionFailed(res)
            return f"a child named {res.name} was born!"
    raise ActionFailed(f"{partner.name} did not respond to your proposal")


# ============================================================== registre
ACTIONS = {
    "move_to": act_move_to,
    "go_to": act_go_to,
    "follow": act_follow,
    "explore": act_explore,
    "wait": act_wait,
    "set_home": act_set_home,
    "gather": act_gather,
    "craft": act_craft,
    "eat": act_eat,
    "build": act_build,
    "continue_build": act_continue_build,
    "place": act_place,
    "write_sign": act_write_sign,
    "demolish": act_demolish,
    "harvest": act_harvest,
    "plant": act_plant,
    "hunt": act_hunt,
    "attack": act_attack,
    "flee": act_flee,
    "lead": act_lead,
    "release": act_release,
    "breed": act_breed,
    "shear": act_shear,
    "tame": act_tame,
    "fish": act_fish,
    "say": act_say,
    "give": act_give,
    "offer_trade": act_offer_trade,
    "accept_trade": act_accept_trade,
    "decline_trade": act_decline_trade,
    "store": act_store,
    "take": act_take,
    "pick_up": act_pick_up,
    "drop": act_drop,
    "sleep": act_sleep,
    "allow": act_allow,
    "propose_child": act_propose_child,
}

# Documentation des actions pour le prompt (paramètres entre parenthèses)
ACTIONS_DOC = """\
move_to(x, y)                      walk to a tile
go_to(target)                      target = person name | "home" | "structure:<id>"
follow(target, ticks)              stay next to a person for a while
explore(direction, distance)       direction: north/south/east/west/northeast/... or random
wait(ticks)
set_home(x, y)                     remember a place as your home
gather(resource, amount, radius?)  resource: wood|stone|coal|iron|gold|diamond|berries|fiber|seeds|sand|clay|mushroom|flint
craft(item, count)                 crafts the item; simple sub-ingredients (planks, sticks, string) are auto-crafted; walks to a known station if needed
eat(item|"best", count)
build(structure, x, y, ...)        see BUILDING below. Materials are taken from your inventory; if you run out, the site pauses and you are told what is missing
continue_build(site_id)            resume a paused site
place(block, x, y)                 place a single block from your inventory (crafting_table, furnace, chest, bed, torch, campfire, door, fence, any wall block, sign, trap, anvil...)
write_sign(x, y, text)             place/write a sign others can read
demolish(x, y, w?, h?) or demolish(site_id)   break blocks/roofs (anyone's) and collect them. Needs time; tools help
plant(item, count, x?, y?)         wheat_seeds on farmland, or sapling on grass
harvest(x?, y?, radius?, replant?) harvest ripe wheat (stage 3) nearby — anyone's crops
hunt(animal, count)                kill animals for their drops (animal = species or "#id")
attack(target, flee_below_hp?)     fight a person (by name) or an animal "#id" until one dies/escapes
flee(from)                         run away from a person
lead(animal, x?, y?)               put a rope_lead on an animal so it follows you (through doors/gates); with x,y you lead it there and release it
release(animal?)                   remove leashes
breed(animal)                      needs 2 adults of that species close together + 2 food (cow/sheep: wheat, chicken: wheat_seeds, pig: berries, wolf: raw_beef)
shear(count)                       get wool from sheep without killing them (needs shears)
tame()                             feed bones to a wild wolf until it becomes yours (it follows and fights for you)
fish(count)                        needs fishing_rod, goes to the nearest shore
say(text, to?)                     speak; everyone within hearing range hears; with 'to' you walk to that person first
give(to, item, count) or give(to, items={...})
offer_trade(to, give={...}, want={...})   propose an exchange; the other decides
accept_trade(offer_id) / decline_trade(offer_id)
store(items={...}|"all", x?, y?)   put items in your nearest own chest (or the chest at x,y)
take(items={...}|"all", x?, y?)    take from a chest (any chest, even someone else's)
pick_up(radius?)                   collect items lying on the ground
drop(item, count)
sleep()                            at night only: sleep until morning (in a bed: heals, safer)
allow(x, y, target, revoke?)       let a person through your iron_door
propose_child(partner)             if both partners propose to each other while standing together, a child is born (each needs hunger>=50, hp>=12; costs 30 hunger each)
"""
