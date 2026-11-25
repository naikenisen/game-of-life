"""Un habitant : état, inventaire, mémoire, plan courant."""
from collections import Counter, deque
from dataclasses import dataclass, field

from . import items as I

TOOL_DURABILITY = {"wooden": 60, "stone": 130, "iron": 250, "diamond": 1500}

NAMES = [
    "Alice", "Bruno", "Chloé", "David", "Emma", "Félix", "Gaëlle", "Hugo", "Inès", "Jules",
    "Katia", "Léo", "Manon", "Nathan", "Océane", "Paul", "Quentin", "Rose", "Samuel", "Tess",
    "Ugo", "Victor", "Wendy", "Xavier", "Yasmine", "Zoé", "Adam", "Bianca", "Camille", "Dimitri",
    "Elsa", "Farid", "Gabin", "Hana", "Ivan", "Jade", "Kylian", "Lina", "Marius", "Nora",
    "Oscar", "Pia", "Raphaël", "Sofia", "Timéo", "Uma", "Valentin", "Wassim", "Yanis", "Zélie",
    "Arthur", "Bérénice", "Côme", "Diane", "Eliott", "Flora", "Gustave", "Héloïse", "Isaac", "Joséphine",
]

FEMALE_NAMES = {"Alice", "Chloé", "Emma", "Gaëlle", "Inès", "Katia", "Manon", "Océane", "Rose", "Tess", "Wendy",
                "Yasmine", "Zoé", "Bianca", "Camille", "Elsa", "Hana", "Jade", "Lina", "Nora", "Pia", "Sofia", "Uma",
                "Zélie", "Bérénice", "Diane", "Flora", "Héloïse", "Joséphine"}

COLORS = [
    (230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180),
    (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255),
    (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195), (128, 128, 0), (255, 215, 180),
    (0, 0, 128), (255, 255, 255), (255, 99, 71), (64, 224, 208), (218, 112, 214), (154, 205, 50),
    (255, 140, 0), (100, 149, 237), (199, 21, 133), (46, 139, 87), (210, 105, 30), (176, 196, 222),
]


@dataclass
class Agent:
    id: int
    name: str
    x: int
    y: int
    color: tuple
    hp: float = 20.0
    hunger: float = 90.0
    energy: float = 90.0             # baisse éveillé, remonte en dormant
    social: float = 70.0             # baisse seul, remonte en parlant / échangeant
    fun: float = 70.0                # baisse en travaillant, remonte en se détendant
    gender: str = "m"
    outfit: int = 0                  # tenue (modèle 3D) ; change avec une armoire
    activity: str = "idle"           # ce que fait le corps (pour l'animation 3D)
    focus: tuple | None = None       # case regardée / travaillée
    seat: tuple | None = None        # meuble occupé
    alive: bool = True
    born: int = 0
    parents: tuple = ()
    inv: Counter = field(default_factory=Counter)
    durability: dict = field(default_factory=dict)   # outil -> usages restants (de l'exemplaire en main)

    # décision / plan
    thought: str = ""
    notes: str = ""
    plan: list = field(default_factory=list)
    step_idx: int = 0
    task: object = None              # générateur en cours
    step_results: list = field(default_factory=list)
    llm_pending: bool = False
    last_call_tick: int = -10_000
    wake_reasons: list = field(default_factory=list)
    urgent: bool = False
    decision_count: int = 0
    last_raw: str = ""
    last_error: str = ""
    routine: list = field(default_factory=list)     # étapes répétées en boucle sans appel LLM
    in_routine: bool = False
    routine_failures: int = 0
    routine_cycles: int = 0
    routine_start: int = 0

    # social / mémoire
    memory: deque = field(default_factory=lambda: deque(maxlen=40))
    inbox: list = field(default_factory=list)
    known: dict = field(default_factory=dict)        # ressource -> (x, y, tick)
    home: tuple | None = None
    child_proposal: tuple | None = None              # (partner_id, tick)
    combat_target: object = None
    sleeping: bool = False
    speech: tuple | None = None                      # (texte, tick de fin)
    kills: int = 0
    death_cause: str = ""
    last_attacker: int | None = None
    attack_cd: int = 0

    @property
    def mood(self):
        """Humeur 0..100 : moyenne des besoins (la faim compte double)."""
        return (2 * self.hunger + self.energy + self.social + self.fun) / 5

    def work_factor(self):
        """Multiplicateur de durée de travail selon la fatigue et l'humeur."""
        f = 1.0
        if self.energy < 15:
            f *= 1.6
        m = self.mood
        if m > 70:
            f *= 0.85
        elif m < 30:
            f *= 1.3
        return f

    def __getstate__(self):
        # l'étape en cours (générateur) ne se sauvegarde pas : elle redémarrera à la reprise
        d = self.__dict__.copy()
        d["task"] = None
        d["llm_pending"] = False
        d["sleeping"] = False
        d["combat_target"] = None
        return d

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def has_boat(self):
        return self.inv.get("boat", 0) > 0

    # ---------------------------------------------------------------- équipement
    def best_tool(self, kind):
        """Renvoie (tier, item) du meilleur outil de ce type possédé, ou (0, None)."""
        best = (0, None)
        for item, tier in I.TOOLS.get(kind, {}).items():
            if self.inv.get(item, 0) > 0 and tier > best[0]:
                best = (tier, item)
        return best

    def weapon(self):
        best, dmg = None, 1
        for item, d in I.MELEE_DAMAGE.items():
            if self.inv.get(item, 0) > 0 and d > dmg:
                best, dmg = item, d
        return best, dmg

    def ranged(self):
        for item, (dmg, rng, ammo) in I.RANGED.items():
            if self.inv.get(item, 0) > 0 and self.inv.get(ammo, 0) > 0:
                return item, dmg, rng, ammo
        return None

    def armor_reduction(self):
        red = max([v for k, v in I.ARMOR.items() if self.inv.get(k, 0) > 0], default=0.0)
        if any(self.inv.get(k, 0) > 0 for k in I.SHIELD):
            red = 1 - (1 - red) * (1 - max(I.SHIELD.values()))
        return red

    def armor_name(self):
        best = max([(v, k) for k, v in I.ARMOR.items() if self.inv.get(k, 0) > 0], default=(0, None))
        return best[1]

    def use_tool(self, item):
        """Use l'outil ; le retire quand sa durabilité tombe à zéro. Renvoie True s'il casse."""
        if item is None or self.inv.get(item, 0) <= 0:
            return False
        tier = item.split("_")[0]
        if item not in self.durability:
            self.durability[item] = TOOL_DURABILITY.get(tier, 100)
        self.durability[item] -= 1
        if self.durability[item] <= 0:
            self.inv[item] -= 1
            if self.inv[item] <= 0:
                del self.inv[item]
            del self.durability[item]
            return True
        return False

    def food_items(self):
        return sorted(((I.FOOD[k], k) for k in self.inv if k in I.FOOD and self.inv[k] > 0), reverse=True)

    def inv_text(self):
        if not self.inv:
            return "empty"
        return ", ".join(f"{k} {v}" for k, v in sorted(self.inv.items()) if v > 0)

    def add(self, item, n=1):
        if n > 0:
            self.inv[item] += n

    def remove(self, item, n=1):
        if self.inv.get(item, 0) < n:
            return False
        self.inv[item] -= n
        if self.inv[item] <= 0:
            del self.inv[item]
        return True
