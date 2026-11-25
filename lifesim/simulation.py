"""Boucle de simulation : métabolisme, exécution des plans, appels LLM, événements sociaux."""
import json
import os
import random
import time
import traceback
from collections import deque

from . import actions as A
from . import items as I
from . import world as W
from .agent import COLORS, FEMALE_NAMES, NAMES, Agent
from .animals import AnimalManager
from .blueprints import Site
from .brain import heuristic_plan
from .llm import LLMClient, build_user_prompt, parse_response, system_prompt


class Logger:
    def __init__(self, log_dir):
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, time.strftime("run_%Y%m%d_%H%M%S.jsonl"))
        self.f = open(self.path, "a", encoding="utf-8")

    def log(self, obj):
        try:
            self.f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.f.flush()
        except Exception:
            pass


ACTIVITY = {
    "gather": lambda s: f"gathering {s.get('resource', '?')}",
    "build": lambda s: f"building a {s.get('structure', '?')}",
    "continue_build": lambda s: f"building site #{s.get('site_id', '?')}",
    "attack": lambda s: f"attacking {s.get('target', '?')}",
    "hunt": lambda s: f"hunting {s.get('animal', '?')}",
    "craft": lambda s: f"crafting {s.get('item', '?')}",
    "say": lambda s: "talking",
    "flee": lambda s: "running away",
    "sleep": lambda s: "sleeping",
    "demolish": lambda s: "demolishing blocks",
    "lead": lambda s: f"leading a {s.get('animal', '?')}",
    "take": lambda s: "taking from a chest",
}


# actions dont l'échec n'empêche pas la suite du plan
NON_BLOCKING = {"say", "give", "offer_trade", "accept_trade", "decline_trade", "eat", "pick_up", "follow",
                "explore", "wait", "sleep", "set_home", "release", "write_sign", "drop", "store", "take",
                "allow", "fish", "shear", "tame", "breed", "harvest", "plant"}


class Simulation:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tick = 0
        self.rng = random.Random(cfg.seed + 1)
        self.world = W.World(cfg)
        self.agents: dict[int, Agent] = {}
        self.structures: dict[int, Site] = {}
        self.trades: dict[int, dict] = {}
        self.events = deque(maxlen=300)
        self.event_total = 0
        self.pending = {}            # agent_id -> (future, tick)
        self._next_site = 1
        self._next_trade = 1
        self._next_agent = 1
        self._used_names = set()
        self.last_save_time = time.time()
        self._connect(cfg)
        self.animals = AnimalManager(self)
        self._spawn_initial_agents()
        self.event(f"Le monde est créé : {len(self.agents)} habitants, "
                   f"{'cerveau heuristique (hors-ligne)' if self.offline else 'LLM ' + cfg.model}.")

    # ================================================================ création
    def _new_name(self):
        for n in NAMES:
            if n not in self._used_names:
                self._used_names.add(n)
                return n
        n = f"Habitant{self._next_agent}"
        self._used_names.add(n)
        return n

    def _spawn_initial_agents(self):
        w = self.world
        cx, cy = w.w // 2, w.h // 2
        placed = []
        tries = 0
        while len(placed) < self.cfg.n_agents and tries < 20000:
            tries += 1
            spread = 25 + tries // 200
            x = max(1, min(w.w - 2, int(self.rng.gauss(cx, spread))))
            y = max(1, min(w.h - 2, int(self.rng.gauss(cy, spread * 0.7))))
            if w.ground[y, x] not in (W.GRASS, W.DIRT) or not w.passable(x, y) or w.feature[y, x] == W.TREE:
                continue
            if any(abs(px - x) + abs(py - y) < 4 for px, py in placed):
                continue
            placed.append((x, y))
            self.add_agent(x, y)

    def add_agent(self, x, y, parents=()):
        aid = self._next_agent
        self._next_agent += 1
        name = self._new_name()
        ag = Agent(aid, name, x, y, COLORS[(aid - 1) % len(COLORS)], hp=self.cfg.max_hp,
                   born=self.tick, parents=parents)
        if name in FEMALE_NAMES or (name not in NAMES and self.rng.random() < 0.5):
            ag.gender = "f"
        ag.outfit = self.rng.randrange(21)
        ag.energy = self.rng.uniform(70, 95)
        ag.social = self.rng.uniform(50, 80)
        ag.fun = self.rng.uniform(50, 80)
        self.agents[aid] = ag
        return ag

    # ================================================================ utilitaires
    def living_agents(self):
        return [a for a in self.agents.values() if a.alive]

    def find_agent(self, name):
        if not name:
            return None
        n = str(name).strip().lower()
        for a in self.agents.values():
            if a.alive and a.name.lower() == n:
                return a
        for a in self.agents.values():
            if a.alive and a.name.lower().startswith(n):
                return a
        return None

    def occupied(self, x, y):
        return any(a.alive and a.x == x and a.y == y for a in self.agents.values()) or bool(self.animals.at(x, y))

    def clock(self):
        dl = self.cfg.day_length
        day = self.tick // dl + 1
        frac = (self.tick % dl) / dl
        minutes = int(((6 + frac * 24) % 24) * 60)
        hour = f"{minutes // 60:02d}:{minutes % 60:02d}"
        night_start = 1 - self.cfg.night_fraction
        if frac < night_start:
            return day, hour, "day", f"night falls in {int((night_start - frac) * dl)} ticks"
        return day, hour, "night", f"morning in {int((1 - frac) * dl)} ticks"

    def is_night(self):
        return (self.tick % self.cfg.day_length) / self.cfg.day_length >= 1 - self.cfg.night_fraction

    def darkness(self):
        """0 = plein jour, 1 = nuit noire (pour l'affichage)."""
        frac = (self.tick % self.cfg.day_length) / self.cfg.day_length
        ns = 1 - self.cfg.night_fraction
        if frac < ns - 0.05:
            return 0.0
        if frac < ns:
            return (frac - (ns - 0.05)) / 0.05
        if frac > 0.97:
            return (1 - frac) / 0.03
        return 1.0

    def event(self, text, pos=None, actors=()):
        self.events.append((self.tick, text))
        self.event_total += 1
        self.logger.log({"type": "event", "tick": self.tick, "text": text})

    def remember(self, ag, text):
        if ag.memory and ag.memory[-1][1] == text:
            return
        ag.memory.append((self.tick, text))

    def wake(self, ag, reason, urgent=False, soft=False):
        """Demande une nouvelle décision. soft=True : simple information, transmise au
        prochain appel sans interrompre le plan en cours (économise des appels LLM)."""
        if not ag.alive:
            return
        if soft:
            ag.inbox.append((self.tick, reason))
            return
        if reason not in ag.wake_reasons:
            ag.wake_reasons.append(reason)
        ag.urgent = ag.urgent or urgent

    def witness(self, pos, text, exclude=()):
        r = self.cfg.witness_radius
        for a in self.living_agents():
            if a.id in exclude:
                continue
            if abs(a.x - pos[0]) <= r and abs(a.y - pos[1]) <= r:
                self.remember(a, f"Tu as vu : {text}")

    def feed(self, ag, item):
        ag.hunger = min(100.0, ag.hunger + I.FOOD[item])

    def new_site(self, ag, kind, x, y, w, h, label, cells):
        s = Site(self._next_site, ag.id, kind, x, y, w, h, label, cells, created=self.tick)
        self.structures[s.id] = s
        self._next_site += 1
        return s

    def current_plan_text(self, ag):
        if ag.step_idx >= len(ag.plan):
            return ""
        parts = []
        for i, st in enumerate(ag.plan):
            if i < ag.step_idx:
                continue
            mark = "(in progress) " if i == ag.step_idx and ag.task is not None else ""
            parts.append(mark + json.dumps(st, ensure_ascii=False))
        return " -> ".join(parts)

    def describe_activity(self, o):
        if o.sleeping:
            return "sleeping"
        if o.step_idx < len(o.plan):
            st = o.plan[o.step_idx]
            f = ACTIVITY.get(st.get("action"))
            return f(st) if f else st.get("action", "busy")
        return "idle"

    # ================================================================ perception
    def update_known(self, ag, radius=30):
        w = self.world
        for res in ("wood", "stone", "coal", "iron", "gold", "diamond", "berries", "fiber", "clay",
                    "mushroom", "flint", "sand"):
            if res == "sand":
                pred = lambda x, y: w.ground[y, x] == W.SAND and w.feature[y, x] == W.NONE
            else:
                feats = W.RESOURCE_FEATURES[res]
                pred = lambda x, y, feats=feats: int(w.feature[y, x]) in feats and w.amount[y, x] > 0 \
                    and w.has_free_neighbor(x, y)
            p = w.find_nearest(ag.x, ag.y, pred, radius)
            if p:
                ag.known[res] = (p[0], p[1], self.tick)
            elif res in ag.known:
                kx, ky, _ = ag.known[res]
                if abs(kx - ag.x) <= radius and abs(ky - ag.y) <= radius:
                    del ag.known[res]  # vérifié : épuisé

    def perceive(self, ag):
        r = self.cfg.view_radius
        w = self.world
        out = {}
        others = []
        for o in self.living_agents():
            if o.id != ag.id and abs(o.x - ag.x) <= r and abs(o.y - ag.y) <= r:
                others.append((o, abs(o.x - ag.x) + abs(o.y - ag.y)))
        out["agents"] = sorted(others, key=lambda t: t[1])[:12]
        animals = {}
        for a in self.animals.near(ag.x, ag.y, r):
            animals.setdefault(a.species, []).append((a, abs(a.x - ag.x) + abs(a.y - ag.y)))
        for sp in animals:
            animals[sp].sort(key=lambda t: t[1])
        out["animals"] = animals
        structs = []
        in_sites = set()
        for s in self.structures.values():
            if s.status == "abandoned" or s.done == 0:
                continue
            if s.x - r <= ag.x <= s.x + s.w + r and s.y - r <= ag.y <= s.y + s.h + r:
                owner = self.agents.get(s.owner)
                who = "yours" if s.owner == ag.id else f"of {owner.name if owner else '?'}" + (
                    " (dead)" if owner and not owner.alive else "")
                structs.append(f"{s.kind} #{s.id} '{s.label}' {who} at ({s.x},{s.y}) {s.w}x{s.h} [{s.status}]")
                for c in s.cells:
                    in_sites.add((c[0], c[1]))
        special = ("crafting_table", "furnace", "anvil", "chest", "bed", "campfire", "sign", "iron_door", "trap",
                   "torch")
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                pos = (ag.x + dx, ag.y + dy)
                b = w.blocks.get(pos)
                if b is None:
                    continue
                if b.type in special or (pos not in in_sites and b.type not in ("torch",)):
                    if pos in in_sites and b.type not in special:
                        continue
                    owner = self.agents.get(b.owner)
                    who = "yours" if b.owner == ag.id else (f"of {owner.name}" if owner else "no owner")
                    extra = f": \"{b.text}\"" if b.type == "sign" and b.text else ""
                    if b.type == "chest":
                        extra = f" (contains {sum(b.inv.values())} items)"
                    structs.append(f"{b.type} at {pos} {who}{extra}")
        # compacter les blocs isolés identiques
        out["structures"] = structs
        ground = []
        for pos, c in w.ground_items.items():
            if abs(pos[0] - ag.x) <= r and abs(pos[1] - ag.y) <= r and c:
                ground.append(f"at {pos}: " + ", ".join(f"{v} {k}" for k, v in c.items()))
        out["ground"] = ground
        ripe = growing = 0
        for pos, c in w.crops.items():
            if abs(pos[0] - ag.x) <= r and abs(pos[1] - ag.y) <= r:
                if c["stage"] >= 3:
                    ripe += 1
                else:
                    growing += 1
        out["crops"] = f"{ripe} ripe wheat, {growing} growing" if ripe or growing else ""
        self.update_known(ag, radius=35)
        res = {}
        for k, (x, y, _t) in sorted(ag.known.items(), key=lambda kv: abs(kv[1][0] - ag.x) + abs(kv[1][1] - ag.y)):
            res[k] = (x, y, abs(x - ag.x) + abs(y - ag.y))
        out["resources"] = res
        wp = w.find_nearest(ag.x, ag.y, lambda x, y: w.ground[y, x] == W.WATER, 40)
        out["water"] = (wp[0], wp[1], abs(wp[0] - ag.x) + abs(wp[1] - ag.y)) if wp else None
        return out

    # ================================================================ social
    def speak(self, ag, text, target=None):
        ag.speech = (text, self.tick + 80)
        ag.social = min(100.0, ag.social + 6)
        self.remember(ag, f"Tu as dit{' à ' + target.name if target else ''} : « {text} »")
        self.event(f"{ag.name}{' → ' + target.name if target else ''} : « {text} »")
        r = self.cfg.hearing_radius
        for o in self.living_agents():
            if o.id == ag.id:
                continue
            if abs(o.x - ag.x) <= r and abs(o.y - ag.y) <= r:
                to_you = target is not None and target.id == o.id
                o.social = min(100.0, o.social + (8 if to_you else 3))
                o.inbox.append((self.tick, f"{ag.name} said{' to you' if to_you else ''}: \"{text}\""))
                if to_you:
                    self.wake(o, f"{ag.name} spoke to you")

    def create_offer(self, ag, target, give, want):
        oid = self._next_trade
        self._next_trade += 1
        offer = {"id": oid, "from": ag.id, "to": target.id, "give": give, "want": want, "expires": self.tick + 2000}
        self.trades[oid] = offer
        g = ", ".join(f"{v} {k}" for k, v in give.items()) or "nothing"
        wt = ", ".join(f"{v} {k}" for k, v in want.items()) or "nothing"
        target.inbox.append((self.tick, f"{ag.name} offers trade #{oid}: gives {g} for {wt}"))
        self.wake(target, f"trade offer #{oid} from {ag.name}")
        self.event(f"{ag.name} propose l'échange #{oid} à {target.name} : {g} contre {wt}")
        return offer

    def on_aggression(self, attacker, target):
        self.witness(attacker.pos, f"{attacker.name} attaque {target.name}", exclude={attacker.id, target.id})
        self.event(f"⚔ {attacker.name} attaque {target.name} !")

    def damage_agent(self, target, dmg, attacker=None, cause="", source=None):
        if not target.alive:
            return False
        red = target.armor_reduction()
        target.hp -= dmg * (1 - red)
        who = attacker.name if attacker is not None else (cause or "quelque chose")
        if target.sleeping and target.task is not None:
            self._cancel_task(target)
        if attacker is not None:
            target.last_attacker = attacker.id
            if not target.memory or "t'attaque" not in target.memory[-1][1] or self.tick - target.memory[-1][0] > 60:
                self.remember(target, f"{who} t'attaque ! (PV {target.hp:.0f})")
            self.wake(target, f"you are being attacked by {who} (your HP {target.hp:.0f})", urgent=True)
            self._reflex_defend(target, attacker)
        else:
            if not target.memory or who not in target.memory[-1][1] or self.tick - target.memory[-1][0] > 60:
                self.remember(target, f"Tu as été blessé par {who} (PV {target.hp:.0f}).")
            self.wake(target, f"you were hurt by {who} (HP {target.hp:.0f})", urgent=True)
            if source is not None:
                self._reflex_defend(target, source)
        if target.hp <= 0:
            self.kill_agent(target, who, attacker)
            return True
        return False

    def _reflex_defend(self, ag, attacker):
        """Réflexe immédiat en attendant la décision du LLM : riposter si armé, sinon fuir."""
        cur = ag.plan[ag.step_idx]["action"] if ag.step_idx < len(ag.plan) else None
        if cur in ("attack", "flee") or ag.combat_target is not None:
            return
        _, dmg = ag.weapon()
        self._cancel_task(ag)
        name = getattr(attacker, "name", None)
        if name is None:  # un animal
            if ag.hp > 6:
                ag.plan = [{"action": "attack", "target": f"#{attacker.id}", "_reflex": True}]
            else:
                ag.plan = [{"action": "flee", "x": attacker.x, "y": attacker.y, "_reflex": True}]
        elif dmg >= 3 and ag.hp > 8:
            ag.plan = [{"action": "attack", "target": name, "flee_below_hp": 6, "_reflex": True}]
        else:
            ag.plan = [{"action": "flee", "from": name, "_reflex": True}]
        ag.step_idx = 0

    def kill_agent(self, ag, cause, killer=None):
        ag.alive = False
        ag.death_cause = cause
        self._cancel_task(ag)
        if ag.inv:
            self.world.drop_items(ag.x, ag.y, ag.inv)
            ag.inv.clear()
        for a in self.animals.animals.values():
            if a.leashed_to == ag.id:
                a.leashed_to = None
            if a.owner == ag.id:
                a.owner = None
        for oid in [k for k, o in self.trades.items() if ag.id in (o["from"], o["to"])]:
            self.trades.pop(oid)
        self.pending.pop(ag.id, None)
        self.event(f"☠ {ag.name} est mort(e) ({cause}).")
        self.witness(ag.pos, f"{ag.name} est mort(e) ({cause}) en ({ag.x},{ag.y})", exclude={ag.id})
        if killer is not None:
            killer.kills += 1
            self.remember(killer, f"Tu as tué {ag.name}.")
            self.wake(killer, f"you killed {ag.name}", soft=True)

    def try_birth(self, a, b):
        if len(self.living_agents()) >= self.cfg.max_population:
            return "the world is full (max population reached)"
        for p in (a, b):
            if p.hunger < 50 or p.hp < 12:
                return f"{p.name} is too weak or hungry (needs hunger>=50 and hp>=12)"
        spot = self.world.find_nearest(a.x, a.y, lambda x, y: self.world.passable(x, y) and not self.occupied(x, y), 4)
        if spot is None:
            return "no room for a child"
        a.hunger -= 30
        b.hunger -= 30
        a.child_proposal = b.child_proposal = None
        child = self.add_agent(spot[0], spot[1], parents=(a.id, b.id))
        child.hunger = 80
        child.hp = 14
        self.remember(child, f"Tu viens de naître. Tes parents sont {a.name} et {b.name}.")
        self.wake(child, "you were just born")
        for p, q in ((a, b), (b, a)):
            self.remember(p, f"Ton enfant {child.name} est né, avec {q.name}.")
        self.event(f"👶 {child.name} est né(e), enfant de {a.name} et {b.name}.")
        return child

    # ================================================================ plans
    def _cancel_task(self, ag):
        ag.activity, ag.focus, ag.seat = "idle", None, None
        if ag.task is not None:
            try:
                ag.task.close()
            except Exception:
                pass
        ag.task = None
        ag.combat_target = None
        ag.sleeping = False
        ag.in_routine = False
        ag.plan = []
        ag.step_idx = 0

    def _start_routine_cycle(self, ag):
        steps = [dict(st) for st in ag.routine]
        # garde-fou : un cycle qui se termine instantanément (tout échoue) ne doit pas tourner à vide
        if ag.in_routine and self.tick - ag.routine_start < 30:
            steps.insert(0, {"action": "wait", "ticks": 150})
        self._set_plan(ag, steps)
        ag.in_routine = True
        ag.routine_start = self.tick
        ag.step_results = ag.step_results[-12:]

    def _set_plan(self, ag, plan, thought="", source="llm"):
        self._cancel_task(ag)
        valid = []
        for st in plan:
            if st.get("action") in A.ACTIONS:
                valid.append(st)
            else:
                ag.step_results.append(f"step '{st.get('action')}' ignored: unknown action")
                ag.last_error = f"unknown action '{st.get('action')}'"
        ag.plan = valid
        ag.step_idx = 0
        if thought:
            ag.thought = thought

    def _run_task(self, ag):
        if ag.task is None:
            if ag.step_idx >= len(ag.plan):
                return
            step = ag.plan[ag.step_idx]
            fn = A.ACTIONS.get(step.get("action"))
            ag.task = fn(self, ag, step)
        step = ag.plan[ag.step_idx]
        label = step.get("action")
        try:
            next(ag.task)
        except StopIteration as e:
            ag.task = None
            ag.activity, ag.focus, ag.seat = "idle", None, None
            ag.step_results.append(f"OK {label}: {e.value}")
            ag.step_idx += 1
            if ag.step_idx >= len(ag.plan) and ag.in_routine:
                ag.routine_failures = 0
                ag.routine_cycles += 1
        except A.ActionFailed as e:
            ag.task = None
            ag.activity, ag.focus, ag.seat = "idle", None, None
            ag.step_results.append(f"FAILED {label}: {e}")
            if label in NON_BLOCKING:
                # étape secondaire : on note l'échec et on poursuit le plan sans rappeler le LLM
                ag.step_idx += 1
                return
            rest = len(ag.plan) - ag.step_idx - 1
            if rest:
                ag.step_results.append(f"({rest} remaining steps cancelled)")
            ag.plan = []
            ag.step_idx = 0
            ag.combat_target = None
            if ag.in_routine:
                ag.routine_failures += 1
                if ag.routine_failures < 2:
                    return  # on retentera la routine au prochain cycle
                self.wake(ag, f"your routine keeps failing ({label}: {e})")
            else:
                self.wake(ag, f"a step failed ({label}: {e})")
        except Exception as e:
            ag.task = None
            ag.step_results.append(f"FAILED {label}: internal error {type(e).__name__}")
            self.logger.log({"type": "crash", "agent": ag.name, "step": step, "trace": traceback.format_exc()})
            ag.plan = []
            ag.step_idx = 0
            self.wake(ag, f"a step failed ({label})")

    # ================================================================ décisions (LLM)
    def _maybe_request(self, ag):
        if ag.id in self.pending:
            return
        plan_done = ag.step_idx >= len(ag.plan) and ag.task is None
        since = self.tick - ag.last_call_tick
        if (plan_done and ag.routine and not ag.wake_reasons and ag.routine_failures < 2
                and since < self.cfg.max_ticks_without_call):
            self._start_routine_cycle(ag)
            return
        if not plan_done and not ag.wake_reasons and since < self.cfg.max_ticks_without_call:
            return
        if not plan_done and not ag.wake_reasons:
            ag.wake_reasons.append("routine check-in")
        if plan_done and not ag.wake_reasons:
            ag.wake_reasons.append(f"periodic check-in (your routine ran {ag.routine_cycles} times)"
                                   if ag.routine else "your plan is finished")
        cfg = self.cfg
        min_gap = cfg.min_ticks_urgent if ag.urgent else (
            cfg.min_ticks_after_plan if plan_done else cfg.min_ticks_between_calls)
        if since < min_gap:
            return
        if self.offline:
            self._apply_decision(ag, heuristic_plan(self, ag))
            ag.last_call_tick = self.tick
            ag.wake_reasons.clear()
            ag.urgent = False
            ag.step_results.clear()
            return
        if self.llm.stats["in_flight"] >= self.cfg.llm_concurrency * 2 and not ag.urgent:
            return
        if self.cfg.budget and self.llm.stats["cost"] >= self.cfg.budget:
            if not getattr(self, "_budget_warned", False):
                self._budget_warned = True
                self.event(f"💰 Budget LLM de ${self.cfg.budget} atteint : passage au cerveau heuristique.")
            self._apply_decision(ag, heuristic_plan(self, ag))
            ag.last_call_tick = self.tick
            ag.wake_reasons.clear()
            ag.urgent = False
            ag.step_results.clear()
            return
        msgs = [{"role": "system", "content": system_prompt(self.cfg, len(self.living_agents()))},
                {"role": "user", "content": build_user_prompt(self, ag)}]
        fut = self.llm.submit(ag.id, msgs)
        self.pending[ag.id] = (fut, self.tick)
        ag.llm_pending = True
        ag.last_call_tick = self.tick
        ag.wake_reasons.clear()
        ag.urgent = False
        ag.step_results.clear()
        ag.inbox.clear()
        ag.last_error = ""

    def _collect_responses(self):
        for aid, (fut, t0) in list(self.pending.items()):
            if not fut.done():
                continue
            del self.pending[aid]
            ag = self.agents.get(aid)
            if ag is None or not ag.alive:
                continue
            ag.llm_pending = False
            try:
                content, err = fut.result()
            except Exception as e:
                content, err = None, str(e)
            if err:
                ag.last_error = f"LLM call failed: {err[:150]}"
                self.event(f"⚠ LLM {ag.name} : {err[:120]}")
                # pour ne pas rester planté : cerveau heuristique en secours
                self._apply_decision(ag, heuristic_plan(self, ag))
                continue
            ag.last_raw = content
            try:
                data = parse_response(content, self.cfg.max_plan_steps)
            except Exception as e:
                ag.last_error = f"your answer was not valid JSON ({e}). Reply with only the JSON object."
                self.wake(ag, "your previous answer could not be parsed")
                continue
            ag.decision_count += 1
            self._apply_decision(ag, data)

    def _apply_decision(self, ag, data):
        thought = str(data.get("thought", ""))[:500]
        if data.get("notes"):
            ag.notes = str(data["notes"])[:400]
        if isinstance(data.get("routine"), list):
            ag.routine = [st for st in data["routine"] if st.get("action") in A.ACTIONS
                          and st.get("action") not in ("propose_child",)]
            ag.routine_failures = 0
            ag.routine_cycles = 0
        keep = bool(data.get("keep_plan")) and ag.step_idx < len(ag.plan)
        if not keep:
            plan = data.get("plan") or []
            if not plan:
                plan = [{"action": "wait", "ticks": 60}]
            self._set_plan(ag, plan, thought)
        elif thought:
            ag.thought = thought
        say = data.get("say")
        if say and isinstance(say, str) and say.strip():
            self.speak(ag, say.strip()[:300])
        self.logger.log({"type": "decision", "tick": self.tick, "agent": ag.name, "thought": thought,
                         "plan": ag.plan, "routine": ag.routine, "keep": keep, "notes": ag.notes})

    # ================================================================ boucle
    def step(self):
        self.tick += 1
        t = self.tick
        cfg = self.cfg
        self.world.update(t)
        self.animals.update(t)
        night = self.is_night()
        if not self.offline:
            self._collect_responses()

        for ag in list(self.agents.values()):
            if not ag.alive:
                continue
            # --- métabolisme
            ag.hunger = max(0.0, ag.hunger - (0.5 if ag.sleeping else 1.0) / cfg.hunger_decay_every)
            if ag.hunger <= 0:
                ag.hp -= cfg.starve_damage
                if t % 300 == 0:
                    self.wake(ag, "you are starving (hunger 0) and losing HP", urgent=True)
            elif ag.hunger > 40:
                ag.hp = min(cfg.max_hp, ag.hp + cfg.regen_rate)
            if night and not self.world.is_warm(ag.x, ag.y):
                ag.hp -= cfg.cold_damage
            # besoins « quotidiens » : énergie, vie sociale, loisirs
            if ag.sleeping:
                in_bed = ag.activity == "sleep_bed"
                ag.energy = min(100.0, ag.energy + (0.4 if in_bed else 0.2))
            else:
                ag.energy = max(0.0, ag.energy - 1 / 15)
            ag.social = max(0.0, ag.social - 1 / 60)
            if t % 10 == 0:  # la simple présence d'autres personnes tout près fait du bien
                company = sum(1 for o in self.agents.values() if o.alive and o is not ag
                              and abs(o.x - ag.x) <= 3 and abs(o.y - ag.y) <= 3)
                ag.social = min(100.0, ag.social + 0.15 * min(company, 3))
            if ag.activity in ("chop", "mine", "dig", "build", "farm", "harvest", "craft"):
                ag.fun = max(0.0, ag.fun - 1 / 20)
            else:
                ag.fun = max(0.0, ag.fun - 1 / 45)
            if t % 600 == 0:
                if ag.energy < 10 and not ag.sleeping:
                    self.wake(ag, f"you are exhausted (energy {ag.energy:.0f}), your work is much slower")
                elif ag.mood < 25:
                    self.wake(ag, f"you feel miserable (mood {ag.mood:.0f}/100)")
            if ag.attack_cd > 0:
                ag.attack_cd -= 1
            if ag.speech and ag.speech[1] < t:
                ag.speech = None
            # piège
            b = self.world.blocks.get(ag.pos)
            if b is not None and b.type == "trap" and b.owner != ag.id:
                self.world.remove_block(*ag.pos)
                owner = self.agents.get(b.owner)
                if owner:
                    self.remember(owner, f"{ag.name} est tombé(e) dans ton piège en {ag.pos}.")
                if self.damage_agent(ag, I.BLOCKS["trap"]["trap_damage"], cause="un piège"):
                    continue
            if ag.hp <= 0:
                self.kill_agent(ag, "la faim" if ag.hunger <= 0 else "le froid")
                continue
            # --- réflexe : manger quand on a faim
            if ag.hunger < 30 and t % 10 == 0:
                foods = ag.food_items()
                if foods:
                    # privilégie la nourriture qui ne gaspille pas trop
                    val, item = min(foods, key=lambda f: abs((100 - ag.hunger) - f[0]) if f[0] <= 100 - ag.hunger else 999 + f[0])
                    ag.remove(item, 1)
                    self.feed(ag, item)
                elif t % 400 == 0:
                    self.wake(ag, f"you are hungry ({ag.hunger:.0f}/100) and carry no food")
            if ag.hp < 6 and t % 300 == 0:
                self.wake(ag, f"your HP is low ({ag.hp:.0f})")
            # --- décisions et exécution
            self._maybe_request(ag)
            self._run_task(ag)

        # rythme de vie : à la tombée de la nuit et au matin, chacun refait le point
        frac = (t % cfg.day_length) / cfg.day_length
        if t % cfg.day_length == int(cfg.day_length * (1 - cfg.night_fraction)) - 30:
            for ag in self.living_agents():
                self.wake(ag, f"night is falling (your energy {ag.energy:.0f})")
        elif t % cfg.day_length == 0 and t > 0:
            for ag in self.living_agents():
                if not ag.sleeping:
                    self.wake(ag, "a new day begins")
        # offres expirées
        if t % 100 == 0:
            for oid in [k for k, o in self.trades.items() if o["expires"] < t]:
                self.trades.pop(oid)
        # propositions d'enfant expirées
        if t % 200 == 0:
            for ag in self.agents.values():
                if ag.child_proposal and t - ag.child_proposal[1] > 600:
                    ag.child_proposal = None

    # ================================================================ sauvegarde
    def _connect(self, cfg):
        """(Re)crée ce qui ne se sauvegarde pas : journal et client LLM."""
        self.logger = Logger(cfg.log_dir)
        self.offline = cfg.offline or not cfg.api_key
        self.llm = None if self.offline else LLMClient(cfg, self.logger)
        self.pending = {}

    def __getstate__(self):
        d = self.__dict__.copy()
        for k in ("llm", "logger", "pending", "_budget_warned"):
            d.pop(k, None)
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self.llm = self.logger = None
        self.pending = {}

    def after_load(self):
        self._connect(self.cfg)
        day, hour, _, _ = self.clock()
        self.event(f"Partie reprise (jour {day}, {hour}) : {len(self.living_agents())} habitants, "
                   f"{'cerveau heuristique (hors-ligne)' if self.offline else 'LLM ' + self.cfg.model}.")

    def shutdown(self):
        if self.llm:
            self.llm.shutdown()
