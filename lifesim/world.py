"""Le territoire : terrain, ressources, blocs construits, toits, objets au sol, cultures."""
import heapq
import random
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from . import items as I

# --- sol ---
WATER, SAND, GRASS, DIRT, FARMLAND, STONE_FLOOR, GRAVEL_GROUND = range(7)
GROUND_NAMES = ["water", "sand", "grass", "dirt", "farmland", "stone_floor", "gravel"]

# --- éléments (features) ---
NONE, TREE, BUSH, TALL_GRASS, ROCK, COAL, IRON, GOLD, DIAMOND, CLAY, MUSHROOM, GRAVEL, SAPLING = range(13)
FEATURE_NAMES = ["none", "tree", "berry_bush", "tall_grass", "rock", "coal_ore", "iron_ore", "gold_ore",
                 "diamond_ore", "clay", "mushroom", "gravel", "sapling"]
SOLID_FEATURES = {ROCK, COAL, IRON, GOLD, DIAMOND}

# ressource (action gather) -> features ciblées
RESOURCE_FEATURES = {
    "wood": {TREE},
    "stone": {ROCK},
    "coal": {COAL},
    "iron": {IRON},
    "gold": {GOLD},
    "diamond": {DIAMOND},
    "berries": {BUSH},
    "fiber": {TALL_GRASS},
    "seeds": {TALL_GRASS},
    "clay": {CLAY},
    "mushroom": {MUSHROOM},
    "flint": {GRAVEL},
    "sand": set(),  # le sable se creuse sur le sol SAND
}

# feature -> (outil requis, tier min, ticks de base par unité, item produit)
HARVEST = {
    TREE: ("axe", 0, 24, "log"),
    ROCK: ("pickaxe", 1, 26, "cobblestone"),
    COAL: ("pickaxe", 1, 30, "coal"),
    IRON: ("pickaxe", 2, 36, "iron_ore"),
    GOLD: ("pickaxe", 3, 40, "gold_ore"),
    DIAMOND: ("pickaxe", 3, 50, "diamond"),
    BUSH: (None, 0, 6, "berries"),
    TALL_GRASS: (None, 0, 5, "fiber"),
    CLAY: ("shovel", 0, 12, "clay"),
    MUSHROOM: (None, 0, 4, "raw_mushroom"),
    GRAVEL: ("shovel", 0, 12, "flint"),
}

# quantité initiale par feature
INITIAL_AMOUNT = {TREE: 4, ROCK: 3, COAL: 3, IRON: 2, GOLD: 2, DIAMOND: 1, BUSH: 3,
                  TALL_GRASS: 1, CLAY: 4, MUSHROOM: 1, GRAVEL: 3}


@dataclass
class Block:
    type: str
    owner: int | None = None
    hp: float = 10
    inv: Counter = field(default_factory=Counter)   # pour les coffres
    structure_id: int | None = None
    text: str = ""                                  # pour les panneaux
    allowed: set = field(default_factory=set)       # porte en fer : qui peut passer


def _value_noise(w, h, cell, rng):
    gw, gh = w // cell + 2, h // cell + 2
    grid = rng.random((gh, gw))
    ys = np.arange(h) / cell
    xs = np.arange(w) / cell
    y0 = ys.astype(int)
    x0 = xs.astype(int)
    fy = ys - y0
    fx = xs - x0
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    a = grid[np.ix_(y0, x0)]
    b = grid[np.ix_(y0, x0 + 1)]
    c = grid[np.ix_(y0 + 1, x0)]
    d = grid[np.ix_(y0 + 1, x0 + 1)]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(w, h, rng, base=32, octaves=4):
    out = np.zeros((h, w))
    amp, total, cell = 1.0, 0.0, base
    for _ in range(octaves):
        out += amp * _value_noise(w, h, max(2, cell), rng)
        total += amp
        amp *= 0.5
        cell //= 2
    return out / total


class World:
    def __init__(self, cfg):
        self.cfg = cfg
        self.w, self.h = cfg.width, cfg.height
        self.rng = random.Random(cfg.seed)
        nrng = np.random.default_rng(cfg.seed)
        self.ground = np.full((self.h, self.w), GRASS, dtype=np.int8)
        self.feature = np.zeros((self.h, self.w), dtype=np.int8)
        self.amount = np.zeros((self.h, self.w), dtype=np.int16)
        self.blocks: dict[tuple, Block] = {}
        self.roofs: dict[tuple, str] = {}
        self.ground_items: dict[tuple, Counter] = {}
        self.crops: dict[tuple, dict] = {}       # pos -> {stage, growth, owner}
        self.light_sources: set = set()
        self.regrow: list = []                   # heap (tick, x, y, feature, amount)
        self.version = 0                         # incrémenté à chaque changement visuel du terrain
        self._generate(nrng)
        # grille de coût de déplacement (liste plate, index y*w+x) :
        #   0 = infranchissable, -1 = eau (franchissable en bateau), sinon coût
        self.dirty = set()
        self.cost = [0.0] * (self.w * self.h)
        for y in range(self.h):
            for x in range(self.w):
                self._update_cell(x, y)

    def mark(self, x, y):
        """Signale une case modifiée (pour la vue 3D)."""
        self.dirty.add((x, y))

    def _update_cell(self, x, y):
        self.dirty.add((x, y))
        i = y * self.w + x
        if self.feature[y, x] in SOLID_FEATURES:
            self.cost[i] = 0
            return
        b = self.blocks.get((x, y))
        if b is not None:
            spec = I.BLOCKS[b.type]
            if spec["solid"] or spec.get("locked"):
                self.cost[i] = 0
                return
        if self.ground[y, x] == WATER:
            self.cost[i] = -1
            return
        f = self.feature[y, x]
        self.cost[i] = 3 if f == TREE else (1.3 if f in (BUSH, TALL_GRASS) else 1)

    # ------------------------------------------------------------------ génération
    def _generate(self, nrng):
        w, h = self.w, self.h
        elev = fbm(w, h, nrng, base=40, octaves=5)
        moist = fbm(w, h, nrng, base=28, octaves=4)
        detail = nrng.random((h, w))
        q_water, q_sand, q_mount = np.quantile(elev, [0.14, 0.19, 0.85])
        q_deep = np.quantile(elev, 0.93)
        q_forest = np.quantile(moist, 0.55)

        g, f, a = self.ground, self.feature, self.amount
        for y in range(h):
            for x in range(w):
                e, m, r = elev[y, x], moist[y, x], detail[y, x]
                if e < q_water:
                    g[y, x] = WATER
                elif e < q_sand:
                    g[y, x] = SAND
                    if r < 0.07:
                        f[y, x] = CLAY
                    elif r < 0.11:
                        f[y, x] = GRAVEL
                elif e > q_mount:
                    g[y, x] = STONE_FLOOR
                    depth = (e - q_mount) / (1 - q_mount + 1e-9)
                    if r < 0.07:
                        f[y, x] = COAL
                    elif r < 0.115:
                        f[y, x] = IRON
                    elif r < 0.125 and e > q_deep:
                        f[y, x] = GOLD
                    elif r < 0.131 and e > q_deep:
                        f[y, x] = DIAMOND
                    elif r < 0.15 and depth < 0.15:
                        f[y, x] = GRAVEL
                        g[y, x] = GRAVEL_GROUND
                    else:
                        f[y, x] = ROCK
                else:
                    g[y, x] = GRASS if r > 0.03 else DIRT
                    if m > q_forest:
                        if r < 0.38:
                            f[y, x] = TREE
                        elif r < 0.41:
                            f[y, x] = MUSHROOM
                        elif r < 0.45:
                            f[y, x] = BUSH
                        elif r < 0.52:
                            f[y, x] = TALL_GRASS
                    else:
                        if r < 0.03:
                            f[y, x] = TREE
                        elif r < 0.08:
                            f[y, x] = BUSH
                        elif r < 0.2:
                            f[y, x] = TALL_GRASS
                        elif r < 0.205:
                            f[y, x] = ROCK
                if f[y, x]:
                    a[y, x] = INITIAL_AMOUNT.get(int(f[y, x]), 1)

    # ------------------------------------------------------------------ requêtes
    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def passable(self, x, y, agent_id=None, boat=False):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return False
        c = self.cost[y * self.w + x]
        if c > 0:
            return True
        if c < 0:
            return boat
        if agent_id is not None:
            b = self.blocks.get((x, y))
            if b is not None and b.type == "iron_door" and (agent_id == b.owner or agent_id in b.allowed):
                return True
        return False

    def animal_passable(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return False
        if self.ground[y, x] == WATER or self.feature[y, x] in SOLID_FEATURES:
            return False
        b = self.blocks.get((x, y))
        if b is not None and I.BLOCKS[b.type]["blocks_animals"]:
            return False
        return True

    def buildable(self, x, y):
        """Une case libre où l'on peut poser un bloc."""
        if not self.in_bounds(x, y):
            return False
        if self.ground[y, x] == WATER:
            return False
        if self.feature[y, x] in SOLID_FEATURES or self.feature[y, x] == TREE:
            return False
        return (x, y) not in self.blocks

    def move_cost(self, x, y):
        c = self.cost[y * self.w + x]
        return 2 if c < 0 else (c or 1)

    def is_warm(self, x, y):
        if (x, y) in self.roofs:
            return True
        for (lx, ly) in self.light_sources:
            b = self.blocks.get((lx, ly))
            if b is None:
                continue
            r = I.BLOCKS[b.type].get("light", 0)
            if abs(lx - x) <= r and abs(ly - y) <= r:
                return True
        return False

    def stations_near(self, x, y, radius=3):
        found = set()
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                b = self.blocks.get((x + dx, y + dy))
                if b is not None and I.BLOCKS[b.type].get("station"):
                    found.add(b.type)
        return found

    def find_nearest(self, x, y, pred, max_r=40):
        """Cherche la case la plus proche (anneaux croissants) satisfaisant pred(x,y)."""
        if pred(x, y):
            return (x, y)
        for r in range(1, max_r + 1):
            best = None
            for dx in range(-r, r + 1):
                for dy in (-r, r) if abs(dx) != r else range(-r, r + 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < self.w and 0 <= ny < self.h and pred(nx, ny):
                        d = abs(dx) + abs(dy)
                        if best is None or d < best[0]:
                            best = (d, (nx, ny))
            if best:
                return best[1]
        return None

    def neighbors4(self, x, y):
        return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))

    def has_free_neighbor(self, x, y, agent_id=None):
        return any(self.passable(nx, ny, agent_id) for nx, ny in self.neighbors4(x, y))

    # ------------------------------------------------------------------ modifications
    def take_feature(self, x, y, tick):
        """Retire une unité de la feature ; renvoie l'id de feature ou None."""
        f = int(self.feature[y, x])
        if f == NONE:
            return None
        self.amount[y, x] -= 1
        self.version += 1
        self.dirty.add((x, y))
        if self.amount[y, x] <= 0:
            self.feature[y, x] = NONE
            self.amount[y, x] = 0
            if f == TREE:
                self.feature[y, x] = SAPLING
                self.amount[y, x] = 1
                heapq.heappush(self.regrow, (tick + self.rng.randint(2500, 4500), x, y, TREE, INITIAL_AMOUNT[TREE]))
            elif f == BUSH:
                self.feature[y, x] = BUSH  # le buisson reste, sans baies
                self.amount[y, x] = 0
                heapq.heappush(self.regrow, (tick + self.rng.randint(500, 1000), x, y, BUSH, 3))
            elif f == TALL_GRASS:
                heapq.heappush(self.regrow, (tick + self.rng.randint(1500, 3000), x, y, TALL_GRASS, 1))
            elif f == MUSHROOM:
                heapq.heappush(self.regrow, (tick + self.rng.randint(2000, 4000), x, y, MUSHROOM, 1))
            elif f == CLAY:
                heapq.heappush(self.regrow, (tick + 6000, x, y, CLAY, 4))
            elif f == GRAVEL:
                heapq.heappush(self.regrow, (tick + 6000, x, y, GRAVEL, 3))
            self._update_cell(x, y)
        return f

    def has_resource(self, x, y, f):
        return self.feature[y, x] == f and self.amount[y, x] > 0

    def place_block(self, x, y, btype, owner=None, structure_id=None):
        spec = I.BLOCKS[btype]
        self.blocks[(x, y)] = Block(btype, owner, spec["hp"], structure_id=structure_id)
        if spec.get("light"):
            self.light_sources.add((x, y))
        if self.feature[y, x] in (TALL_GRASS, MUSHROOM, BUSH, SAPLING, GRAVEL, CLAY):
            self.feature[y, x] = NONE
            self.amount[y, x] = 0
        self._update_cell(x, y)
        self.version += 1

    def remove_block(self, x, y):
        b = self.blocks.pop((x, y), None)
        self.light_sources.discard((x, y))
        if b is not None:
            if b.inv:
                self.drop_items(x, y, b.inv)
            self._update_cell(x, y)
            self.version += 1
        return b

    def drop_items(self, x, y, counter):
        c = self.ground_items.setdefault((x, y), Counter())
        for k, v in counter.items():
            if v > 0:
                c[k] += v

    def pick_items(self, x, y):
        return self.ground_items.pop((x, y), Counter())

    def update(self, tick):
        # repousse des ressources
        while self.regrow and self.regrow[0][0] <= tick:
            _, x, y, f, amt = heapq.heappop(self.regrow)
            if (x, y) in self.blocks:
                continue
            if f in (BUSH,) or self.feature[y, x] in (NONE, SAPLING):
                self.feature[y, x] = f
                self.amount[y, x] = amt
                self._update_cell(x, y)
                self.version += 1
        # croissance des cultures (toutes les 20 ticks)
        if tick % 20 == 0:
            for (x, y), c in self.crops.items():
                if c["stage"] >= 3:
                    continue
                near_water = any(
                    0 <= x + dx < self.w and 0 <= y + dy < self.h and self.ground[y + dy, x + dx] == WATER
                    for dx in range(-4, 5) for dy in range(-4, 5))
                c["growth"] += 2 if near_water else 1
                if c["growth"] >= 25:
                    c["growth"] = 0
                    c["stage"] += 1
                    self.version += 1
                    self.dirty.add((x, y))

    # ------------------------------------------------------------------ pathfinding
    def find_path(self, start, goals, agent_id=None, boat=False, max_nodes=12000):
        """A* 4-directions vers l'un des goals (set de positions). Renvoie une liste de cases (sans start)."""
        if not goals:
            return None
        if start in goals:
            return []
        W_ = self.w
        H_ = self.h
        cost = self.cost
        goal_idx = {gy * W_ + gx for gx, gy in goals if 0 <= gx < W_ and 0 <= gy < H_}
        if not goal_idx:
            return None
        # heuristique admissible : distance au centre des buts moins leur étalement
        gx_c = sum(g[0] for g in goals) / len(goals)
        gy_c = sum(g[1] for g in goals) / len(goals)
        spread = max(abs(g[0] - gx_c) + abs(g[1] - gy_c) for g in goals)
        s_idx = start[1] * W_ + start[0]
        open_h = [(0.0, 0.0, s_idx)]
        came = {s_idx: -1}
        gcost = {s_idx: 0.0}
        n = 0
        while open_h:
            _, g, cur = heapq.heappop(open_h)
            if cur in goal_idx:
                path = []
                while cur != s_idx:
                    path.append((cur % W_, cur // W_))
                    cur = came[cur]
                path.reverse()
                return path
            if g > gcost[cur]:
                continue
            n += 1
            if n > max_nodes:
                return None
            cx, cy = cur % W_, cur // W_
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if nx < 0 or ny < 0 or nx >= W_ or ny >= H_:
                    continue
                ni = ny * W_ + nx
                c = cost[ni]
                if c <= 0:
                    if c < 0 and boat:
                        c = 2
                    elif c == 0 and agent_id is not None and self.passable(nx, ny, agent_id):
                        c = 1
                    else:
                        continue
                ng = g + c
                if ng < gcost.get(ni, 1e18):
                    gcost[ni] = ng
                    came[ni] = cur
                    hh = abs(nx - gx_c) + abs(ny - gy_c) - spread
                    heapq.heappush(open_h, (ng + (hh if hh > 0 else 0), ng, ni))
        return None

    def adjacent_goals(self, x, y, agent_id=None, boat=False):
        return {p for p in self.neighbors4(x, y) if self.passable(p[0], p[1], agent_id, boat)}
