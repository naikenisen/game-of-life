"""Animaux : errance, fuite, laisse, domestication, reproduction, loups."""
import random
from dataclasses import dataclass

from . import items as I
from . import world as W

INITIAL_COUNTS = {"sheep": 26, "cow": 22, "pig": 22, "chicken": 26, "wolf": 6}


@dataclass
class Animal:
    id: int
    species: str
    x: int
    y: int
    hp: float
    age: int = 2000            # < 1500 = bébé
    leashed_to: int | None = None
    owner: int | None = None   # loup apprivoisé
    flee_from: tuple | None = None
    flee_ticks: int = 0
    breed_cooldown: int = 0
    attack_cd: int = 0
    target: object = None      # cible d'un loup
    alive: bool = True
    egg_timer: int = 0

    @property
    def spec(self):
        return I.ANIMALS[self.species]

    @property
    def adult(self):
        return self.age >= 1500

    @property
    def pos(self):
        return (self.x, self.y)


class AnimalManager:
    def __init__(self, sim):
        self.sim = sim
        self.world = sim.world
        self.rng = random.Random(sim.cfg.seed + 7)
        self.animals: dict[int, Animal] = {}
        self.next_id = 1
        for sp, n in INITIAL_COUNTS.items():
            for _ in range(n):
                self.spawn_wild(sp, initial=True)

    def spawn(self, species, x, y, age=2000):
        a = Animal(self.next_id, species, x, y, I.ANIMALS[species]["hp"], age=age,
                   egg_timer=self.rng.randint(800, 2000))
        self.animals[a.id] = a
        self.next_id += 1
        return a

    def spawn_wild(self, species, initial=False):
        w = self.world
        for _ in range(200):
            x, y = self.rng.randrange(w.w), self.rng.randrange(w.h)
            g = w.ground[y, x]
            if g not in (W.GRASS, W.DIRT) or not w.animal_passable(x, y):
                continue
            if species == "wolf" and w.feature[y, x] != W.NONE and not initial:
                pass
            if not initial and any(abs(ag.x - x) + abs(ag.y - y) < 18 for ag in self.sim.living_agents()):
                continue
            return self.spawn(species, x, y)
        return None

    def at(self, x, y):
        return [a for a in self.animals.values() if a.x == x and a.y == y and a.alive]

    def near(self, x, y, r, species=None):
        out = []
        for a in self.animals.values():
            if a.alive and abs(a.x - x) <= r and abs(a.y - y) <= r and (species is None or a.species == species):
                out.append(a)
        return out

    def kill(self, a, killer=None):
        a.alive = False
        drops = dict(a.spec["drops"])
        if not a.adult:
            drops = {k: max(1, v // 2) for k, v in drops.items()}
        self.animals.pop(a.id, None)
        return drops

    def damage(self, a, dmg, attacker_pos=None, attacker=None):
        a.hp -= dmg
        if attacker_pos:
            a.flee_from = attacker_pos
            a.flee_ticks = 30
        if a.species == "wolf" and attacker is not None and a.owner is None:
            a.target = attacker
        return a.hp <= 0

    # ------------------------------------------------------------------ déplacement
    def _can(self, a, x, y):
        if a.leashed_to is not None:
            return self.world.passable(x, y, agent_id=a.leashed_to)
        return self.world.animal_passable(x, y)

    def _step_toward(self, a, tx, ty, away=False):
        opts = []
        for nx, ny in self.world.neighbors4(a.x, a.y):
            if not self._can(a, nx, ny):
                continue
            d = abs(nx - tx) + abs(ny - ty)
            opts.append((-d if away else d, self.rng.random(), nx, ny))
        if opts:
            opts.sort()
            _, _, a.x, a.y = opts[0]

    def _follow(self, a, ag):
        d = abs(a.x - ag.x) + abs(a.y - ag.y)
        if d > 20:
            return False  # laisse cassée
        if d > 2:
            path = self.world.find_path(a.pos, self.world.adjacent_goals(ag.x, ag.y, ag.id) | {ag.pos},
                                        agent_id=ag.id, max_nodes=800)
            if path:
                a.x, a.y = path[0]
            else:
                self._step_toward(a, ag.x, ag.y)
        return True

    def update(self, tick):
        sim = self.sim
        is_night = sim.is_night()
        for a in list(self.animals.values()):
            if not a.alive:
                continue
            a.age += 1
            if a.breed_cooldown > 0:
                a.breed_cooldown -= 1
            if a.attack_cd > 0:
                a.attack_cd -= 1
            # œufs
            if a.species == "chicken" and a.adult:
                a.egg_timer -= 1
                if a.egg_timer <= 0:
                    a.egg_timer = self.rng.randint(1200, 2400)
                    self.world.drop_items(a.x, a.y, {"egg": 1})
            # pièges
            b = self.world.blocks.get(a.pos)
            if b is not None and b.type == "trap" and self.rng.random() < 0.05:
                if self.damage(a, I.BLOCKS["trap"]["trap_damage"]):
                    self.world.drop_items(a.x, a.y, self.kill(a))
                    continue

            speed = a.spec["speed"]
            if a.leashed_to is not None:
                ag = sim.agents.get(a.leashed_to)
                if ag is None or not ag.alive:
                    a.leashed_to = None
                elif tick % 2 == 0 and not self._follow(a, ag):
                    a.leashed_to = None
                    sim.remember(ag, f"La laisse du {a.species} #{a.id} s'est cassée (trop loin).")
                continue

            if a.species == "wolf":
                self._wolf(a, tick, is_night)
                continue

            if tick % speed != 0:
                continue
            if a.flee_ticks > 0 and a.flee_from:
                a.flee_ticks -= 1
                self._step_toward(a, *a.flee_from, away=True)
            elif self.rng.random() < 0.35:
                nx, ny = self.rng.choice(self.world.neighbors4(a.x, a.y))
                if self._can(a, nx, ny):
                    a.x, a.y = nx, ny

        # repeuplement de la faune sauvage
        if tick % 300 == 0:
            counts = {}
            for a in self.animals.values():
                counts[a.species] = counts.get(a.species, 0) + 1
            for sp, n in INITIAL_COUNTS.items():
                if counts.get(sp, 0) < n * 0.5:
                    self.spawn_wild(sp)

    def _wolf(self, a, tick, is_night):
        sim = self.sim
        # loup apprivoisé : suit son maître et défend
        if a.owner is not None:
            owner = sim.agents.get(a.owner)
            if owner is None or not owner.alive:
                a.owner = None
                return
            tgt = owner.combat_target
            if tgt is not None and getattr(tgt, "alive", False):
                self._chase_and_bite(a, tgt)
            elif tick % 2 == 0:
                self._follow(a, owner)
            return
        if tick % a.spec["speed"] != 0:
            return
        tgt = a.target
        if tgt is not None and (not getattr(tgt, "alive", False) or abs(tgt.x - a.x) + abs(tgt.y - a.y) > 9
                                or (not is_night and not isinstance(tgt, Animal) and tgt.combat_target is not a)):
            tgt = a.target = None
        if tgt is None and (is_night or self.rng.random() < 0.002):
            # chasse : proies ou humains dehors la nuit
            best, bd = None, 7
            for p in self.near(a.x, a.y, 6):
                if p.species in ("sheep", "chicken", "pig") and abs(p.x - a.x) + abs(p.y - a.y) < bd:
                    best, bd = p, abs(p.x - a.x) + abs(p.y - a.y)
            if is_night:
                for ag in sim.living_agents():
                    d = abs(ag.x - a.x) + abs(ag.y - a.y)
                    if d < min(bd, 5) and not self.world.is_warm(ag.x, ag.y):
                        best, bd = ag, d
            a.target = tgt = best
        if tgt is not None:
            self._chase_and_bite(a, tgt)
        elif self.rng.random() < 0.4:
            nx, ny = self.rng.choice(self.world.neighbors4(a.x, a.y))
            if self._can(a, nx, ny):
                a.x, a.y = nx, ny

    def _chase_and_bite(self, a, tgt):
        d = abs(tgt.x - a.x) + abs(tgt.y - a.y)
        if d <= 1:
            if a.attack_cd == 0:
                a.attack_cd = 12
                dmg = a.spec.get("damage", 2)
                if isinstance(tgt, Animal):
                    if self.damage(tgt, dmg, a.pos):
                        self.kill(tgt)
                        a.target = None
                else:
                    self.sim.damage_agent(tgt, dmg, attacker=None, cause="un loup", source=a)
        else:
            self._step_toward(a, tgt.x, tgt.y)
