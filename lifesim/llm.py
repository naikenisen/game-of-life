"""Appels au LLM (OpenRouter) : construction du prompt, appel asynchrone, parsing JSON."""
import json
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import items as I
from .actions import ACTIONS_DOC

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# noms d'actions que les petits modèles inventent souvent -> action réelle
ACTION_ALIASES = {
    "smelt": "craft", "cook": "craft", "make": "craft", "mine": "gather", "chop": "gather", "collect": "gather",
    "harvest_resource": "gather", "go": "move_to", "walk": "move_to", "walk_to": "move_to", "goto": "go_to",
    "talk": "say", "speak": "say", "fight": "attack", "kill": "attack", "trade": "offer_trade",
    "build_house": "build", "construct": "build", "rest": "sleep", "pickup": "pick_up", "idle": "wait",
    "place_block": "place", "farm": "harvest",
}


_SYS_CACHE = {}


def system_prompt(cfg, n_people):
    # identique pour tous les habitants -> profite du cache de prompt des fournisseurs
    n_people = (n_people // 10) * 10 or n_people
    key = (cfg.language, n_people, cfg.width, cfg.height)
    if key not in _SYS_CACHE:
        _SYS_CACHE[key] = _system_prompt(cfg, n_people)
    return _SYS_CACHE[key]


def _system_prompt(cfg, n_people):
    lang = cfg.language
    foods = ", ".join(f"{k} {v}" for k, v in sorted(I.FOOD.items(), key=lambda kv: -kv[1]))
    return f"""You are a person living in a 2D world seen from above: a grid of {cfg.width}x{cfg.height} tiles, x grows to the east, y grows to the south. About {n_people} people live here (your own identity is given in each message); each one decides for themselves. Nobody gives you goals or orders: you decide what you want to do with your life, how you treat others, and what you build.

You only take the high-level decisions. Your plan is executed automatically step by step (walking, path-finding, gathering, building block by block, fighting). You will be asked again only when your whole plan is finished, when an important step fails, or when something important happens to you (attack, someone talking to you, a trade offer). So plan ahead for a long stretch of time: give a long plan that keeps you busy (typically 6 to 15 steps). If a secondary step fails (say, give, trade, eat, follow, explore...), the rest of the plan still runs.
You can also set a ROUTINE: a list of steps you repeat in a loop, on your own, every time your plan is finished (for example a work cycle). While you have a routine, you are not asked again unless something important happens, a routine step fails twice in a row, or after a long time. Change it whenever your life changes; send "routine": [] to drop it.

WORLD RULES
- Time: a day lasts {cfg.day_length} ticks (1 tick = about one step of walking). Night is the last {int(cfg.night_fraction * 100)}% of each day.
- Survival: hunger goes from 100 down to 0 (-1 every {cfg.hunger_decay_every} ticks). At 0 hunger you lose HP. HP max {cfg.max_hp:.0f}; it slowly regenerates when hunger > 40. At 0 HP you die for good and everything you carry falls on the ground. When your hunger gets low you automatically eat food you carry.
- At night, being outside without a roof over your tile and with no light source nearby (torch, campfire, furnace) slowly hurts you. Wolves roam and hunt at night.
- Terrain: water (not walkable unless you carry a boat), sand, grass, forests, mountains of rock containing coal, iron, gold and diamond ores. Rock and ore tiles block movement until mined out. Gravel gives flint. Clay is found near water.
- Trees regrow from saplings; berry bushes and tall grass regrow.
- Tools: a pickaxe is needed to mine rock and coal, stone_pickaxe+ for iron, iron_pickaxe+ for gold and diamond. Axes and shovels make work faster. A hoe is needed to make farmland. Tools and weapons wear out.
- Blocks: walls (planks, cobblestone, brick, log, glass, iron_block) and fences block everyone. door and fence_gate let people through but never animals. iron_door: only its owner and people they allow. A roof tile on a tile shelters whoever stands under it.
- Ownership is not enforced by the world: anybody can demolish anybody's blocks, open anybody's chest, harvest anybody's crops, take items lying on the ground. People nearby may notice.
- Animals: sheep, cow, pig and chicken wander freely; they cannot cross walls, fences, gates or doors. A rope_lead makes an animal follow you (also through gates). Animals can be hunted, bred, sheared (sheep); chickens lay eggs. Wolves are dangerous but can be tamed with bones.
- Combat: anyone can attack anyone. Damage: fist 1, swords 4-7, axes 3-6, spear 5, bow 6 at range <= 8 (uses arrows). Armor (leather/iron/diamond) and shield reduce damage taken.
- Farming: wheat_seeds planted on farmland grow in 4 stages (faster within 4 tiles of water); harvesting a ripe plant gives wheat and seeds.
- Crafting stations (crafting_table, furnace, campfire, anvil) must be placed in the world; recipes needing one work within 3 tiles of it (anyone's station).
- Children are born when two people both choose it (propose_child) while together.
- Daily needs (0-100): energy (drops while awake, restored by sleeping, much faster in a bed), social (drops when alone, rises when talking with people, eating together, dancing near others), fun (drops, faster while working; rises when relaxing, reading, sitting on a sofa, eating at a table, dancing). Your mood is the average of your needs (hunger counts double). Good mood makes you work faster; bad mood or exhaustion makes you slower.
- Furniture (table, chair, stool, sofa, bookshelf, wardrobe, nightstand, rug, lamp, plant_pot, barrel, bed...) can be placed anywhere, inside houses with furnish() or build(custom), and used with use(). Others can see your home and what is inside.

RECIPES (count output <- inputs @station). 'fuel' means one of: {', '.join(I.FUEL_ITEMS)}.
{I.recipes_prompt_text()}

FOOD (hunger restored): {foods}

ACTIONS (use these exact names and parameter names):
{ACTIONS_DOC}
BUILDING with build(structure=..., ...):
- "house": x, y (top-left corner), w, h (3..14), material (wall block, default planks), roof (roof material or "none"), door ("door"|"iron_door"|"fence_gate"|"none"), door_side (north/south/east/west), name. Walls go around the rectangle from (x,y) to (x+w-1,y+h-1). It needs 2*w+2*h-5 wall blocks + 1 door + w*h roof material. Walls are placed first, then the roof.
- "enclosure": x, y, w, h (3..24), material (default fence), door (default fence_gate).
- "wall": from (x,y) to (x2,y2), material.
- "farm": x, y, w, h: tills the area into farmland and plants wheat_seeds (needs a hoe + seeds). plant=false to only till.
- "roof": x, y, w, h, material: covers an area (for example walls you built before).
- "custom": x, y, cells=[[dx,dy,"cobblestone"],[dx,dy,"roof:planks"],[dx,dy,"farmland"],...] any shape you want, any placeable block.
Trees on the building area are cut automatically. If materials run out the site pauses and you are told what is missing.

ANSWER FORMAT: reply with ONE JSON object and nothing else:
{{
  "thought": "your short reasoning, in {lang}",
  "say": "optional: words you say aloud right now (people nearby hear), in {lang}",
  "notes": "optional: rewrite your personal long-term notes (goals, places, opinions about people), max 400 chars, in {lang}",
  "routine": [ ...steps... ]   (optional, up to 10 steps repeated in a loop after your plan; [] = no routine; omit to keep the current one),
  "keep_plan": false,   (true = keep executing your current unfinished plan instead of a new one)
  "plan": [ {{"action": "...", ...parameters}}, ... ]   (up to {cfg.max_plan_steps} steps, executed in order; prefer long plans)
}}"""


def _fmt_counts(d):
    return ", ".join(f"{v} {k}" for k, v in d.items()) or "nothing"


def build_user_prompt(sim, ag):
    cfg = sim.cfg
    w = sim.world
    p = sim.perceive(ag)
    lines = []
    day, hour, phase, until = sim.clock()
    lines.append(f"TIME: day {day}, {hour}, it is {phase} ({until}). Tick {sim.tick}.")
    warm = "yes" if w.is_warm(ag.x, ag.y) else "no"
    lines.insert(0, f"You are {ag.name}.")
    lines.append(f"YOU: {ag.name}, at ({ag.x},{ag.y}), HP {ag.hp:.0f}/{cfg.max_hp:.0f}, hunger {ag.hunger:.0f}/100, "
                 f"sheltered/warm here: {warm}. Home: {ag.home or 'none'}.")
    wpn, dmg = ag.weapon()
    rd = ag.ranged()
    lines.append(f"NEEDS: energy {ag.energy:.0f}, social {ag.social:.0f}, fun {ag.fun:.0f} -> mood {ag.mood:.0f}/100")
    lines.append(f"COMBAT: melee {wpn or 'fist'} (damage {dmg})" + (f", ranged {rd[0]} ({ag.inv.get(rd[3], 0)} {rd[3]})" if rd else "")
                 + f", armor {ag.armor_name() or 'none'}.")
    lines.append(f"INVENTORY: {ag.inv_text()}")
    if ag.notes:
        lines.append(f"YOUR NOTES: {ag.notes}")
    mine = [s for s in sim.structures.values() if s.owner == ag.id and s.status != "abandoned"]
    if mine:
        lines.append("YOUR BUILDINGS/SITES:")
        for s in mine[-8:]:
            lines.append("  " + s.summary())
    leashed = [a for a in sim.animals.animals.values() if a.leashed_to == ag.id]
    tamed = [a for a in sim.animals.animals.values() if a.owner == ag.id]
    if leashed or tamed:
        lines.append("YOUR ANIMALS: " + ", ".join(f"{a.species} #{a.id}{' (leashed)' if a.leashed_to == ag.id else ''}"
                                                   for a in leashed + tamed))

    lines.append(f"PEOPLE IN SIGHT (radius {cfg.view_radius}):")
    if p["agents"]:
        for o, d in p["agents"]:
            wo, _ = o.weapon()
            extra = f", holds {wo}" if wo else ""
            arm = o.armor_name()
            extra += f", wears {arm}" if arm else ""
            act = sim.describe_activity(o)
            lines.append(f"  {o.name} at ({o.x},{o.y}) dist {d}, HP {o.hp:.0f}{extra}; {act}")
    else:
        lines.append("  nobody")
    if p["animals"]:
        parts = []
        for sp, lst in p["animals"].items():
            a, d = lst[0]
            tag = ""
            parts.append(f"{len(lst)} {sp} (nearest #{a.id} at ({a.x},{a.y}) dist {d}{tag})")
        lines.append("ANIMALS IN SIGHT: " + "; ".join(parts))
    if p["structures"]:
        lines.append("BUILDINGS/BLOCKS IN SIGHT:")
        for txt in p["structures"][:14]:
            lines.append("  " + txt)
    if p["ground"]:
        lines.append("ITEMS ON THE GROUND: " + "; ".join(p["ground"][:6]))
    if p["crops"]:
        lines.append("CROPS IN SIGHT: " + p["crops"])
    lines.append("RESOURCES (nearest known locations):")
    for res, (x, y, d) in p["resources"].items():
        lines.append(f"  {res}: ({x},{y}) dist {d}")
    if p["water"]:
        lines.append(f"  water: ({p['water'][0]},{p['water'][1]}) dist {p['water'][2]}")
    if ag.inbox:
        lines.append("WHAT YOU HEARD / RECEIVED SINCE LAST TIME:")
        for t, txt in ag.inbox[-10:]:
            lines.append(f"  [t{t}] {txt}")
    offers = [o for o in sim.trades.values() if o["to"] == ag.id]
    if offers:
        lines.append("TRADE OFFERS FOR YOU:")
        for o in offers:
            frm = sim.agents[o["from"]].name
            lines.append(f"  offer #{o['id']} from {frm}: gives {_fmt_counts(o['give'])} / wants {_fmt_counts(o['want'])}")
    if ag.memory:
        lines.append("YOUR RECENT MEMORIES:")
        for t, txt in list(ag.memory)[-12:]:
            lines.append(f"  [t{t}] {txt}")
    if ag.routine:
        lines.append(f"YOUR ROUTINE (repeated {ag.routine_cycles} times so far): "
                     + " -> ".join(json.dumps(st, ensure_ascii=False) for st in ag.routine))
    cur = sim.current_plan_text(ag)
    if cur:
        lines.append("YOUR CURRENT PLAN (still running): " + cur)
    if ag.step_results:
        lines.append("RESULTS OF YOUR LAST PLAN:")
        for r in ag.step_results[-12:]:
            lines.append(f"  {r}")
    if ag.last_error:
        lines.append(f"PROBLEM WITH YOUR LAST ANSWER: {ag.last_error}")
    reasons = "; ".join(dict.fromkeys(ag.wake_reasons)) or "your plan is finished"
    lines.append(f"WHY YOU ARE ASKED NOW: {reasons}")
    lines.append("What do you do next? Answer with the JSON object only.")
    return "\n".join(lines)


# ---------------------------------------------------------------- parsing
def parse_response(text, max_steps=15):
    if not text:
        raise ValueError("empty response")
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object found")
    depth, end, in_str, esc = 0, -1, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    blob = t[start:end + 1] if end > 0 else t[start:]
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        fixed = re.sub(r",\s*([}\]])", r"\1", blob)
        data = json.loads(fixed)
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object")
    data = {str(k).strip().lstrip("+").lower(): v for k, v in data.items()}
    data["plan"] = _clean_steps(data.get("plan", []), max_steps)
    if "routine" in data:
        data["routine"] = _clean_steps(data.get("routine") or [], 10)
    return data


def _clean_steps(plan, max_steps):
    if isinstance(plan, dict):
        plan = [plan]
    if not isinstance(plan, list):
        plan = []
    clean = []
    for step in plan[:max_steps]:
        if isinstance(step, dict) and "action" in step:
            step = dict(step)
            step["action"] = ACTION_ALIASES.get(str(step["action"]).strip().lower(),
                                                str(step["action"]).strip().lower())
            # certains modèles imbriquent les paramètres
            if isinstance(step.get("params"), dict):
                step.update(step.pop("params"))
            if isinstance(step.get("parameters"), dict):
                step.update(step.pop("parameters"))
            clean.append(step)
    return clean


# ---------------------------------------------------------------- client
class LLMClient:
    def __init__(self, cfg, logger=None):
        self.cfg = cfg
        self.pool = ThreadPoolExecutor(max_workers=cfg.llm_concurrency)
        self.logger = logger
        self.lock = threading.Lock()
        self.stats = {"calls": 0, "ok": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0,
                      "in_flight": 0, "last_latency": 0.0, "cost": 0.0}
        self.last_error = ""

    def submit(self, agent_id, messages):
        with self.lock:
            self.stats["calls"] += 1
            self.stats["in_flight"] += 1
        return self.pool.submit(self._call, agent_id, messages)

    def _call(self, agent_id, messages):
        t0 = time.time()
        body = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.llm_temperature,
            "max_tokens": self.cfg.llm_max_tokens,
            "response_format": {"type": "json_object"},
            "usage": {"include": True},
            "reasoning": {"enabled": False},
        }
        content, err, usage = None, None, {}
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    API_URL, data=json.dumps(body).encode("utf-8"),
                    headers={"Authorization": f"Bearer {self.cfg.api_key}",
                             "Content-Type": "application/json",
                             "X-Title": "LifeSim"})
                with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout) as r:
                    resp = json.loads(r.read().decode("utf-8"))
                if "error" in resp:
                    raise RuntimeError(str(resp["error"])[:300])
                content = resp["choices"][0]["message"].get("content") or ""
                usage = resp.get("usage") or {}
                err = None
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                err = f"HTTP {e.code}: {detail}"
                if e.code == 400 and "reasoning" in body:
                    body.pop("reasoning")  # modèle à raisonnement obligatoire
                    continue
                if e.code == 400 and "response_format" in body:
                    body.pop("response_format")  # modèle sans mode JSON
                    continue
                if e.code in (401, 402, 403):
                    break
                time.sleep(1.5 * (attempt + 1))
            except Exception as e:  # réseau, timeout, JSON...
                err = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
        latency = time.time() - t0
        with self.lock:
            self.stats["in_flight"] -= 1
            self.stats["last_latency"] = latency
            if err:
                self.stats["errors"] += 1
                self.last_error = err
            else:
                self.stats["ok"] += 1
                self.stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
                self.stats["completion_tokens"] += usage.get("completion_tokens", 0)
                self.stats["cost"] += float(usage.get("cost", 0) or 0)
        if self.logger:
            self.logger.log({"type": "llm", "agent": agent_id, "latency": round(latency, 2), "error": err,
                             "prompt": messages[-1]["content"], "response": content})
        return content, err

    def shutdown(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
