#!/usr/bin/env python3
"""LifeSim — simulation de vie où 30 habitants pilotés par un LLM (OpenRouter)
survivent, construisent, cultivent, élèvent, commercent... ou se battent.

    python main.py                 # avec fenêtre pygame et LLM (clé dans .env)
    python main.py --offline       # sans LLM (cerveau heuristique), pour tester
    python main.py --headless --ticks 3000   # sans affichage
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lifesim.config import Config, load_dotenv  # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser(description="LifeSim : simulation de vie pilotée par LLM")
    ap.add_argument("--agents", type=int, default=30, help="nombre d'habitants au départ")
    ap.add_argument("--model", type=str, default=None, help="modèle OpenRouter (ex: mistralai/mistral-small-3.2-24b-instruct)")
    ap.add_argument("--seed", type=int, default=None, help="graine du monde")
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--tps", type=int, default=None, help="ticks par seconde (vitesse x1)")
    ap.add_argument("--concurrency", type=int, default=None, help="appels LLM simultanés max")
    ap.add_argument("--language", type=str, default=None, help="langue des pensées/dialogues (défaut French)")
    ap.add_argument("--think-interval", type=int, default=None,
                    help="ticks minimum avant qu'un habitant occupé soit ré-interrogé (défaut 400 ; plus haut = moins cher)")
    ap.add_argument("--budget", type=float, default=0.0, help="dépense LLM max en $ (0 = illimité)")
    ap.add_argument("--load", nargs="?", const="saves/world.pkl", default=None, metavar="FICHIER",
                    help="reprendre une partie sauvegardée (défaut saves/world.pkl)")
    ap.add_argument("--save", type=str, default="saves/world.pkl", metavar="FICHIER",
                    help="fichier de sauvegarde (auto toutes les 5 min et à la fermeture)")
    ap.add_argument("--no-save", action="store_true", help="ne jamais sauvegarder")
    ap.add_argument("--offline", action="store_true", help="sans LLM : cerveau heuristique")
    ap.add_argument("--headless", action="store_true", help="sans fenêtre")
    ap.add_argument("--serve", action="store_true",
                    help="mode serveur pour la vue 3D Godot (pas de fenêtre pygame) ; vitesse par défaut 2 ticks/s")
    ap.add_argument("--port", type=int, default=7777, help="port TCP du mode --serve")
    ap.add_argument("--ticks", type=int, default=2000, help="durée en mode headless")
    ap.add_argument("--screenshot", type=str, default=None, help="(headless) enregistre une image PNG de la carte à la fin")
    return ap.parse_args()


def _sigterm(_signum, _frame):
    raise KeyboardInterrupt  # même chemin que Ctrl+C : sauvegarde puis arrêt propre


def main():
    import signal
    signal.signal(signal.SIGTERM, _sigterm)
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    args = parse_args()
    cfg = Config()
    cfg.n_agents = args.agents
    if args.model:
        cfg.model = args.model
    if args.seed is not None:
        cfg.seed = args.seed
    if args.width:
        cfg.width = args.width
    if args.height:
        cfg.height = args.height
    if args.tps:
        cfg.ticks_per_second = args.tps
    elif args.serve:
        cfg.ticks_per_second = 2  # vitesse « réaliste » pour la 3D : ~marche humaine, 1 jour = 10 min
    if args.concurrency:
        cfg.llm_concurrency = args.concurrency
    if args.language:
        cfg.language = args.language
    cfg.offline = args.offline
    cfg.budget = args.budget
    if args.think_interval:
        cfg.min_ticks_between_calls = args.think_interval
    if not cfg.offline and not cfg.api_key:
        print("⚠ Pas de OPENROUTER_API_KEY trouvée (.env) : passage en mode hors-ligne.")

    from lifesim import persistence
    from lifesim.simulation import Simulation
    base = os.path.dirname(os.path.abspath(__file__))
    save_path = None if args.no_save else os.path.join(base, args.save)
    load_path = os.path.join(base, args.load) if args.load else None
    if load_path and os.path.exists(load_path):
        sim = persistence.load(load_path, cfg)
        day, hour, _, _ = sim.clock()
        print(f"Partie reprise depuis {load_path} : jour {day} {hour}, tick {sim.tick}, "
              f"{len(sim.living_agents())} habitants vivants.")
    else:
        if load_path:
            print(f"Pas de sauvegarde trouvée ({load_path}) : nouveau monde.")
        elif save_path and os.path.exists(save_path):
            # on ne perd jamais une partie : l'ancienne sauvegarde est mise de côté
            backup = save_path.replace(".pkl", time.strftime("_%Y%m%d_%H%M%S.pkl"))
            os.replace(save_path, backup)
            print(f"Nouvelle partie. L'ancienne sauvegarde a été conservée sous {backup} "
                  f"(reprendre avec --load {os.path.relpath(backup, base)}).")
        sim = Simulation(cfg)
        print(f"Monde {cfg.width}x{cfg.height}, {cfg.n_agents} habitants, "
              f"{'hors-ligne' if sim.offline else 'modèle ' + cfg.model}.")
    sim.save_path = save_path
    print(f"Journal : {sim.logger.path}" + (f" | sauvegarde : {save_path}" if save_path else ""))

    try:
        if args.serve:
            run_server(sim, args.port)
        elif args.headless:
            run_headless(sim, args.ticks)
            if args.screenshot:
                save_screenshot(sim, args.screenshot)
        else:
            from lifesim.render import App
            App(sim).run()
    except KeyboardInterrupt:
        pass
    finally:
        if save_path:
            persistence.save(sim, save_path)
            print(f"Partie sauvegardée : {save_path} (reprendre avec --load)")
        sim.shutdown()


def run_headless(sim, n):
    last_ev = 0
    t0 = time.time()
    tick_interval = 1.0 / sim.cfg.ticks_per_second if not sim.offline else 0
    for _ in range(n):
        t_start = time.time()
        sim.step()
        new = sim.event_total - last_ev
        if new:
            for t, txt in list(sim.events)[-new:]:
                print(f"[t{t:>6}] {txt}")
            last_ev = sim.event_total
        if sim.tick % 3000 == 0 and getattr(sim, "save_path", None):
            from lifesim import persistence
            persistence.save(sim, sim.save_path)
        if sim.tick % 500 == 0:
            alive = len(sim.living_agents())
            st = sim.llm.stats if sim.llm else {}
            print(f"--- tick {sim.tick} | vivants {alive} | chantiers {len(sim.structures)} | "
                  f"blocs {len(sim.world.blocks)} | LLM {st}")
        # en mode LLM on garde un rythme réel pour laisser le temps aux réponses
        dt = time.time() - t_start
        if tick_interval > dt:
            time.sleep(tick_interval - dt)
    print(f"Terminé en {time.time() - t0:.1f}s")


def run_server(sim, port):
    from lifesim import persistence
    from lifesim.bridge import Bridge
    bridge = Bridge(sim, port=port)
    bridge.start()
    print(f"Serveur 3D prêt sur 127.0.0.1:{port} — lancez la vue Godot (./run3d.sh). Ctrl+C pour arrêter.")
    paused = False
    next_t = time.time()
    last_status = 0
    while True:
        for cmd in bridge.poll_commands():
            c = cmd.get("cmd")
            if c == "speed":
                sim.cfg.ticks_per_second = max(1, min(60, int(cmd.get("tps", 2))))
            elif c == "pause":
                paused = bool(cmd.get("value", not paused))
            elif c == "save" and getattr(sim, "save_path", None):
                persistence.save(sim, sim.save_path)
                sim.event("💾 Partie sauvegardée.")
        if not paused:
            sim.step()
        bridge.broadcast(paused)
        if getattr(sim, "save_path", None) and time.time() - sim.last_save_time > 300:
            persistence.save(sim, sim.save_path)
        if time.time() - last_status > 30:
            last_status = time.time()
            day, hour, _, _ = sim.clock()
            st = sim.llm.stats if sim.llm else {}
            print(f"[jour {day} {hour}] tick {sim.tick} | vivants {len(sim.living_agents())} | "
                  f"clients 3D {bridge.n_clients()} | LLM appels {st.get('calls', 0)} coût ${st.get('cost', 0):.3f}")
        next_t += 1.0 / sim.cfg.ticks_per_second
        delay = next_t - time.time()
        if delay > 0:
            time.sleep(delay)
        else:
            next_t = time.time()


def save_screenshot(sim, path):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    from lifesim.render import App
    app = App(sim)
    app.zoom = 6.0
    app.cam_x, app.cam_y = 0, 0
    app.clamp_cam()
    app.draw()
    pygame.image.save(app.screen, path)
    print(f"Capture enregistrée : {path}")


if __name__ == "__main__":
    main()
