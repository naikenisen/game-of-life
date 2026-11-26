"""Vie intérieure des habitants : mémoire à long terme, relations, réflexion quotidienne.

Inspiré des « Generative Agents » (Park et al., 2023), en version économe :
- chaque souvenir reçoit une importance (1..10) calculée par le code, sans appel LLM ;
- on ne montre au LLM que les souvenirs les plus utiles maintenant :
  score = récence + importance + pertinence (personnes présentes ou citées, mots communs
  avec la situation) — une pertinence lexicale à la place des embeddings, gratuite ;
- les relations (affinité, familiarité, liens familiaux) évoluent avec les interactions ;
- une fois par jour simulé, pendant la nuit, chacun « réfléchit » : un appel LLM court
  transforme les souvenirs de la journée en conclusions durables et en opinions sur
  les autres (ou une version heuristique gratuite hors-ligne).
"""
import json
import math
import re

LONGMEM_MAX = 160          # souvenirs à long terme conservés par habitant
LONGMEM_MIN_IMPORTANCE = 4  # en dessous, le souvenir ne reste que dans la mémoire récente
REFLECT_MIN_NEW = 12       # importance cumulée minimale depuis la dernière réflexion

# --------------------------------------------------------------------- importance
_RULES = [
    (9, r"\bnaître\b|\bnée?\b.*enfant|ton enfant|tes parents|tu as tué|est mort|est morte|est mort\(e\)"),
    (8, r"t'attaque|tu as été blessé|attaque\b|a tué|détruit"),
    (7, r"propose d'avoir un enfant|piège"),
    (6, r"récolté ton blé|de ton blé|refusé ton échange|laisse .* cassée"),
    (5, r"t'a donné|accepté ton échange|échange"),
    (3, r"^tu as vu"),
    (2, r"^tu as dit"),
]
_RULES = [(imp, re.compile(rx, re.IGNORECASE)) for imp, rx in _RULES]


def rate_importance(text):
    """Importance 1..10 d'un souvenir, par règles simples (gratuit, déterministe)."""
    for imp, rx in _RULES:
        if rx.search(text):
            return imp
    return 3


# --------------------------------------------------------------------- noms
class NameIndex:
    """Retrouve les habitants cités dans un texte (mots entiers, insensible à la casse)."""

    def __init__(self):
        self._key = None
        self._rx = None
        self._ids = {}

    def find(self, sim, text):
        key = len(sim.agents)
        if key != self._key:
            self._key = key
            names = sorted((a.name for a in sim.agents.values()), key=len, reverse=True)
            self._ids = {a.name.lower(): a.id for a in sim.agents.values()}
            self._rx = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE) \
                if names else None
        if self._rx is None:
            return ()
        return tuple(dict.fromkeys(self._ids[m.lower()] for m in self._rx.findall(text)
                                   if m.lower() in self._ids))


NAMES = NameIndex()


# --------------------------------------------------------------------- mémoire
def store(sim, ag, text, importance=None, about=None, kind="event"):
    """Ajoute un souvenir à la mémoire à long terme s'il est assez important."""
    imp = rate_importance(text) if importance is None else int(importance)
    if imp < LONGMEM_MIN_IMPORTANCE and kind == "event":
        return
    if any(m[1] == text for m in ag.longmem[-12:]):
        return  # déjà en mémoire (conclusion répétée, même événement)
    if about is None:
        about = tuple(i for i in NAMES.find(sim, text) if i != ag.id)
    ag.longmem.append((sim.tick, text, imp, tuple(about), kind))
    ag.mem_since_reflect += imp
    if len(ag.longmem) > LONGMEM_MAX:
        # on oublie le souvenir le moins marquant (les vieux souvenirs banals partent d'abord)
        day = sim.cfg.day_length
        worst = min(range(len(ag.longmem) - 20),
                    key=lambda i: ag.longmem[i][2] - (sim.tick - ag.longmem[i][0]) / day
                    + (3 if ag.longmem[i][4] == "reflection" else 0))
        ag.longmem.pop(worst)


_WORD = re.compile(r"[a-zà-ÿ]{4,}", re.IGNORECASE)
_STOP = {"your", "with", "from", "that", "this", "have", "were", "there", "about", "dans", "pour", "avec",
         "elle", "vous", "nous", "sont", "être", "tick", "ticks"}


def _words(text):
    return {w.lower() for w in _WORD.findall(text)} - _STOP


def recall(sim, ag, k=6, context_ids=(), context_text="", exclude_ticks=(), kinds=("event", "reflection")):
    """Les k souvenirs à long terme les plus utiles maintenant (récence + importance + pertinence)."""
    if not ag.longmem:
        return []
    ctx_ids = set(context_ids)
    ctx_words = _words(context_text)
    day = sim.cfg.day_length
    scored = []
    for m in ag.longmem:
        t, text, imp, about, kind = m
        if kind not in kinds or (t in exclude_ticks and kind == "event"):
            continue
        recency = math.exp(-(sim.tick - t) / (1.5 * day))
        relevance = 0.0
        if ctx_ids and ctx_ids.intersection(about):
            relevance += 1.0
        if ctx_words:
            common = len(ctx_words & _words(text))
            relevance += min(0.6, 0.2 * common)
        scored.append((recency + imp / 10 + relevance, m))
    scored.sort(key=lambda s: -s[0])
    return sorted((m for _s, m in scored[:k]), key=lambda m: m[0])


# --------------------------------------------------------------------- relations
def rel(ag, other_id):
    r = ag.rel.get(other_id)
    if r is None:
        r = ag.rel[other_id] = {"aff": 0.0, "n": 0, "last": 0, "opinion": "", "bond": ""}
    return r


def relate(sim, ag, other, delta, interaction=True):
    """Modifie ce que `ag` ressent pour `other` (affinité -100..100)."""
    if other is None or other.id == ag.id:
        return
    r = rel(ag, other.id)
    # les premières impressions comptent plus, les sentiments installés bougent moins vite
    inertia = 1.0 if r["n"] < 5 else 0.7
    r["aff"] = max(-100.0, min(100.0, r["aff"] + delta * inertia))
    if interaction:
        r["n"] += 1
    r["last"] = sim.tick


def bond(ag, other, label):
    rel(ag, other.id)["bond"] = label


def feeling(aff):
    if aff >= 60:
        return "close friend"
    if aff >= 25:
        return "friend"
    if aff >= 8:
        return "you like them"
    if aff > -8:
        return "neutral"
    if aff > -30:
        return "you dislike them"
    if aff > -60:
        return "you resent them"
    return "enemy"


def relations_text(sim, ag, present_ids=(), limit=8):
    """Lignes « PEOPLE YOU KNOW » : présents d'abord, puis les liens les plus forts."""
    if not ag.rel:
        return []
    items = []
    for oid, r in ag.rel.items():
        o = sim.agents.get(oid)
        if o is None or (not r["bond"] and r["n"] == 0 and abs(r["aff"]) < 3):
            continue
        weight = (100 if oid in present_ids else 0) + (60 if r["bond"] else 0) + abs(r["aff"]) + min(r["n"], 20)
        items.append((weight, o, r))
    items.sort(key=lambda it: -it[0])
    out = []
    for _w, o, r in items[:limit]:
        parts = [feeling(r["aff"]) + f" (affinity {r['aff']:+.0f})", f"{r['n']} interactions"]
        if r["bond"]:
            parts.insert(0, r["bond"])
        if not o.alive:
            parts.insert(0, "DEAD")
        line = f"  {o.name}: " + ", ".join(parts)
        if r["opinion"]:
            line += f'; your opinion: "{r["opinion"]}"'
        out.append(line)
    return out


def drift_company(sim, ag, near):
    """Passer du temps ensemble rapproche un peu (appelé périodiquement)."""
    for o in near:
        r = rel(ag, o.id)
        if r["aff"] < 40:
            relate(sim, ag, o, 0.4, interaction=False)


# --------------------------------------------------------------------- réflexion
REFLECT_SYSTEM = """You are the inner voice of a person living in a small world. Once a day, at night, the person looks back on what happened and draws lasting conclusions. Answer with ONE JSON object only:
{{
  "insights": [ {{"text": "a lasting conclusion about your life, the world or the people around you, in {lang}, max 160 chars", "importance": 1-10}} ],  (1 to 3 items)
  "opinions": {{ "PersonName": "your current opinion of this person, in {lang}, max 100 chars" }},  (only people who matter to you)
  "goals": "your long-term goals and wishes for the coming days, in {lang}, max 300 chars"
}}"""


def reflect_due(sim, ag):
    return ag.alive and ag.mem_since_reflect >= REFLECT_MIN_NEW


def reflect_prompt(sim, ag):
    day, hour, _, _ = sim.clock()
    since = ag.last_reflect_tick
    lines = [f"You are {ag.name}. It is day {day}, {hour}.",
             f"Needs: hunger {ag.hunger:.0f}, energy {ag.energy:.0f}, social {ag.social:.0f}, fun {ag.fun:.0f}, "
             f"mood {ag.mood:.0f}/100. HP {ag.hp:.0f}."]
    if ag.notes:
        lines.append(f"Your current goals/notes: {ag.notes}")
    refl = [m for m in ag.longmem if m[4] == "reflection"][-5:]
    if refl:
        lines.append("What you had concluded before:")
        lines += [f"  - {m[1]}" for m in refl]
    rels = relations_text(sim, ag, limit=10)
    if rels:
        lines.append("People you know:")
        lines += rels
    recent = [m for m in ag.longmem if m[0] > since and m[4] == "event"]
    recent += [(t, txt, 2, (), "event") for t, txt in ag.memory if t > since]
    seen, events = set(), []
    for m in sorted(recent, key=lambda m: m[0]):
        if m[1] not in seen:
            seen.add(m[1])
            events.append(m)
    lines.append("What happened since your last reflection (importance 1-10):")
    for t, txt, imp, _a, _k in events[-30:]:
        lines.append(f"  [t{t}] ({imp}) {txt}")
    if ag.thought:
        lines.append(f"Your last thought: {ag.thought}")
    lines.append("Reflect. Answer with the JSON object only.")
    return "\n".join(lines)


def reflect_messages(sim, ag):
    return [{"role": "system", "content": REFLECT_SYSTEM.format(lang=sim.cfg.language)},
            {"role": "user", "content": reflect_prompt(sim, ag)}]


def parse_reflection(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object")
    blob = t[a:b + 1]
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = json.loads(re.sub(r",\s*([}\]])", r"\1", blob))
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def apply_reflection(sim, ag, data):
    n = 0
    for it in (data.get("insights") or [])[:3]:
        if isinstance(it, str):
            it = {"text": it, "importance": 7}
        if not isinstance(it, dict) or not str(it.get("text", "")).strip():
            continue
        try:
            imp = max(5, min(10, int(it.get("importance", 7))))
        except (TypeError, ValueError):
            imp = 7
        store(sim, ag, str(it["text"]).strip()[:200], importance=imp, kind="reflection")
        n += 1
    ops = data.get("opinions") or {}
    if isinstance(ops, dict):
        for name, op in list(ops.items())[:8]:
            o = sim.find_agent(name) or next((a for a in sim.agents.values() if a.name.lower() == str(name).lower()),
                                              None)
            if o is not None and o.id != ag.id and isinstance(op, str):
                rel(ag, o.id)["opinion"] = op.strip()[:120]
    goals = data.get("goals")
    if isinstance(goals, str) and goals.strip():
        ag.notes = goals.strip()[:400]
    ag.mem_since_reflect = 0
    ag.last_reflect_tick = sim.tick
    ag.reflections += 1
    sim.logger.log({"type": "reflection", "tick": sim.tick, "agent": ag.name, "data": data})
    return n


def heuristic_reflection(sim, ag):
    """Réflexion gratuite (hors-ligne) : tire des conclusions simples des relations et des souvenirs."""
    since = ag.last_reflect_tick
    recent = [m for m in ag.longmem if m[0] > since and m[4] == "event"]
    insights, opinions = [], {}
    friends = sorted(((r["aff"], oid) for oid, r in ag.rel.items() if r["aff"] >= 25), reverse=True)
    foes = sorted((r["aff"], oid) for oid, r in ag.rel.items() if r["aff"] <= -25)
    if friends:
        o = sim.agents[friends[0][1]]
        insights.append({"text": f"Je peux compter sur {o.name}.", "importance": 7})
    if foes:
        o = sim.agents[foes[0][1]]
        insights.append({"text": f"Je dois me méfier de {o.name}.", "importance": 8})
    dangers = [m for m in recent if m[2] >= 8]
    if any("loup" in m[1] for m in dangers):
        insights.append({"text": "Les loups rôdent la nuit : je dois dormir à l'abri ou près d'un feu.", "importance": 7})
    elif any("mort" in m[1] for m in dangers):
        insights.append({"text": "La mort peut frapper n'importe qui ici, il faut prendre soin des siens.",
                         "importance": 8})
    elif dangers:
        insights.append({"text": "Journée difficile, je dois être plus prudent·e.", "importance": 7})
    if ag.mood < 35:
        insights.append({"text": "Je ne suis pas heureux·se en ce moment, il faut que ça change.", "importance": 6})
    elif ag.mood > 75 and not dangers:
        insights.append({"text": "La vie est douce en ce moment.", "importance": 5})
    for aff, oid in friends[:2] + foes[:2]:
        o = sim.agents[oid]
        opinions[o.name] = ("quelqu'un de bien" if aff >= 60 else "plutôt sympathique") if aff > 0 else \
            ("un danger" if aff <= -60 else "pas digne de confiance")
    return {"insights": insights[:3], "opinions": opinions}
