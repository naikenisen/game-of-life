"""Sauvegarde / reprise d'une partie.

On sérialise tout l'état (monde, habitants, animaux, chantiers, échanges...) avec
pickle. Ce qui ne peut pas être sauvegardé est reconstruit à la reprise :
  - l'étape en cours de chaque habitant (un générateur Python) redémarre au début
    de cette étape ; le plan, la routine et les chantiers sont conservés ;
  - les appels LLM en vol sont abandonnés (l'habitant redemandera une décision) ;
  - le client LLM et le journal sont recréés avec les options du lancement courant.

Attention : pickle peut exécuter du code ; ne chargez que vos propres sauvegardes.
"""
import os
import pickle
import time

SAVE_VERSION = 1
DEFAULT_PATH = os.path.join("saves", "world.pkl")


def save(sim, path=DEFAULT_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump({"version": SAVE_VERSION, "saved_at": time.time(), "sim": sim}, f,
                    protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)  # écriture atomique : une sauvegarde interrompue n'écrase pas la précédente
    sim.last_save_time = time.time()
    return path


def load(path, runtime_cfg):
    """Recharge une partie. Les options d'exécution (clé, modèle, budget, vitesse, hors-ligne...)
    viennent du lancement courant ; la taille et la graine du monde viennent de la sauvegarde."""
    with open(path, "rb") as f:
        data = pickle.load(f)
    if data.get("version") != SAVE_VERSION:
        raise ValueError(f"sauvegarde de version {data.get('version')} incompatible (attendu {SAVE_VERSION})")
    sim = data["sim"]
    cfg = sim.cfg
    for k in ("model", "api_key", "llm_concurrency", "budget", "offline", "language", "ticks_per_second",
              "min_ticks_between_calls", "log_dir"):
        setattr(cfg, k, getattr(runtime_cfg, k))
    sim.after_load()
    return sim
