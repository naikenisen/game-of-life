"""Paramètres globaux de la simulation (modifiables aussi en ligne de commande)."""
import os
from dataclasses import dataclass, field


def load_dotenv(path=".env"):
    """Mini-parseur de .env (évite une dépendance)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Config:
    # monde
    width: int = 160
    height: int = 110
    seed: int = 42
    n_agents: int = 30
    max_population: int = 60

    # temps
    ticks_per_second: int = 10
    day_length: int = 1200          # ticks pour un jour complet
    night_fraction: float = 0.35    # part de la journée qui est la nuit

    # métabolisme
    max_hp: float = 20.0
    hunger_decay_every: int = 60    # -1 faim tous les N ticks
    starve_damage: float = 0.05     # par tick quand faim = 0
    regen_rate: float = 0.02        # par tick si faim > 40
    cold_damage: float = 0.006      # par tick dehors la nuit sans toit / feu

    # LLM
    model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "mistralai/mistral-small-3.2-24b-instruct"))
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    llm_concurrency: int = 12
    budget: float = 0.0                  # $ max dépensés en LLM (0 = illimité), ensuite cerveau heuristique
    llm_timeout: float = 60.0
    llm_temperature: float = 0.8
    llm_max_tokens: int = 1000           # plans plus longs -> un peu plus de tokens de sortie
    max_plan_steps: int = 15
    min_ticks_between_calls: int = 400   # par agent, pour interrompre un plan en cours (hors urgence)
    min_ticks_after_plan: int = 120      # délai minimal entre deux décisions quand le plan est fini
    min_ticks_urgent: int = 60           # délai minimal en cas d'urgence (attaque...)
    max_ticks_without_call: int = 4000   # on redemande au LLM au moins aussi souvent
    language: str = "French"             # langue des pensées / dialogues
    reflection: bool = True              # réflexion du soir par LLM (1 appel court / habitant / jour)
    offline: bool = False                # True = cerveau heuristique sans LLM

    # perception
    view_radius: int = 14
    hearing_radius: int = 12
    witness_radius: int = 15

    log_dir: str = "logs"
