"""Pont réseau entre la simulation (Python) et la vue 3D (Godot).

Protocole : TCP, un message JSON par ligne (UTF-8).
  serveur -> client
    {"type":"init", ...}   à la connexion : terrain complet, blocs, toits, cultures, chantiers, habitants
    {"type":"tick", ...}   à chaque tick : horloge, habitants, animaux, cases modifiées, événements
  client -> serveur
    {"cmd":"speed","tps":4}   {"cmd":"pause","value":true}   {"cmd":"save"}

La simulation tourne dans le thread principal ; chaque client a son propre thread
d'envoi (file bornée) pour qu'un client lent ne ralentisse jamais la simulation.
"""
import json
import queue
import socket
import threading

from . import items as I

TOOL_FOR = {"chop": "axe", "mine": "pickaxe", "dig": "shovel", "farm": "hoe", "fish": "fishing_rod"}


class _Client:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.q = queue.Queue(maxsize=200)
        self.alive = True
        self.ready = False
        self.rbuf = b""

    def send_loop(self):
        try:
            while self.alive:
                data = self.q.get()
                if data is None:
                    break
                self.conn.sendall(data)
        except OSError:
            pass
        self.alive = False

    def push(self, data):
        try:
            self.q.put_nowait(data)
        except queue.Full:
            self.alive = False  # client trop lent : on le déconnecte


class Bridge:
    def __init__(self, sim, host="127.0.0.1", port=7777):
        self.sim = sim
        self.host, self.port = host, port
        self.clients = []
        self.lock = threading.Lock()
        self.commands = queue.Queue()
        self.server = None
        self._last_sites = None
        self._prev_pos = {}
        self._prev_apos = {}
        self._ev_sent = sim.event_total
        self._people_n = len(sim.agents)

    # ------------------------------------------------------------------ réseau
    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(4)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while True:
            try:
                conn, addr = self.server.accept()
            except OSError:
                return
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            c = _Client(conn, addr)
            threading.Thread(target=c.send_loop, daemon=True).start()
            threading.Thread(target=self._recv_loop, args=(c,), daemon=True).start()
            with self.lock:
                self.clients.append(c)

    def _recv_loop(self, c):
        try:
            while c.alive:
                chunk = c.conn.recv(4096)
                if not chunk:
                    break
                c.rbuf += chunk
                while b"\n" in c.rbuf:
                    line, c.rbuf = c.rbuf.split(b"\n", 1)
                    try:
                        self.commands.put(json.loads(line.decode("utf-8")))
                    except Exception:
                        pass
        except OSError:
            pass
        c.alive = False

    def poll_commands(self):
        out = []
        while True:
            try:
                out.append(self.commands.get_nowait())
            except queue.Empty:
                return out

    def n_clients(self):
        with self.lock:
            return sum(1 for c in self.clients if c.alive)

    def shutdown(self):
        with self.lock:
            for c in self.clients:
                c.alive = False
                c.q.put(None)
                try:
                    c.conn.close()
                except OSError:
                    pass
        if self.server:
            self.server.close()

    # ------------------------------------------------------------------ messages
    @staticmethod
    def _encode(obj):
        return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    def _cell(self, x, y):
        w = self.sim.world
        b = w.blocks.get((x, y))
        c = w.crops.get((x, y))
        return [x, y, int(w.ground[y, x]), int(w.feature[y, x]), int(w.amount[y, x]),
                b.type if b else "", b.owner if b and b.owner is not None else -1,
                w.roofs.get((x, y), ""), c["stage"] if c else -1]

    def _sites(self):
        return [[s.id, s.kind, s.x, s.y, s.w, s.h, s.owner, s.label, s.status]
                for s in self.sim.structures.values() if s.done > 0]

    def _agent_static(self, ag):
        return {"id": ag.id, "name": ag.name, "gender": ag.gender, "color": list(ag.color)}

    def _agent(self, ag):
        moved = self._prev_pos.get(ag.id) not in (None, ag.pos)
        self._prev_pos[ag.id] = ag.pos
        act = ag.activity
        tool = ""
        if act in TOOL_FOR:
            _, tool = ag.best_tool(TOOL_FOR[act])
            tool = tool or ""
        elif act == "build":
            tool = "hammer"
        elif act == "fight" or ag.combat_target is not None:
            act = "fight"
            rd = ag.ranged()
            tool = rd[0] if rd else (ag.weapon()[0] or "")
        focus = ag.focus
        if ag.combat_target is not None and getattr(ag.combat_target, "alive", False):
            focus = (ag.combat_target.x, ag.combat_target.y)
        step = ag.plan[ag.step_idx]["action"] if ag.step_idx < len(ag.plan) else ""
        d = {
            "id": ag.id, "x": ag.x, "y": ag.y, "alive": ag.alive, "mv": moved,
            "act": act, "fx": focus[0] if focus else None, "fy": focus[1] if focus else None,
            "seat": list(ag.seat) if ag.seat else None, "tool": tool, "outfit": ag.outfit,
            "hp": round(ag.hp, 1), "hu": round(ag.hunger), "en": round(ag.energy), "so": round(ag.social),
            "fu": round(ag.fun), "mood": round(ag.mood), "say": ag.speech[0] if ag.speech else "",
            "th": ag.thought, "step": step, "think": ag.llm_pending, "routine": bool(ag.in_routine),
            "plan": [s.get("action", "") for s in ag.plan[ag.step_idx:ag.step_idx + 6]],
            "inv": {k: v for k, v in ag.inv.items() if v > 0},
            "notes": ag.notes, "home": list(ag.home) if ag.home else None, "kills": ag.kills,
            "mem": [m for _t, m in list(ag.memory)[-6:]], "death": ag.death_cause,
        }
        return d

    def _animal(self, a):
        moved = self._prev_apos.get(a.id) not in (None, a.pos)
        self._prev_apos[a.id] = a.pos
        return [a.id, a.species, a.x, a.y, 1 if a.adult else 0, 1 if moved else 0,
                1 if a.flee_ticks > 0 else 0, a.owner if a.owner is not None else -1,
                a.leashed_to if a.leashed_to is not None else -1]

    def init_message(self):
        sim, w, cfg = self.sim, self.sim.world, self.sim.cfg
        return {
            "type": "init", "w": w.w, "h": w.h, "tick": sim.tick, "tps": cfg.ticks_per_second,
            "day_length": cfg.day_length, "night_fraction": cfg.night_fraction,
            "ground": w.ground.flatten().tolist(), "feature": w.feature.flatten().tolist(),
            "amount": w.amount.flatten().tolist(),
            "blocks": [[x, y, b.type, b.owner if b.owner is not None else -1] for (x, y), b in w.blocks.items()],
            "roofs": [[x, y, m] for (x, y), m in w.roofs.items()],
            "crops": [[x, y, c["stage"]] for (x, y), c in w.crops.items()],
            "sites": self._sites(),
            "people": [self._agent_static(a) for a in sim.agents.values()],
            "agents": [self._agent(a) for a in sim.agents.values()],
            "lights": {k: v["light"] for k, v in I.BLOCKS.items() if v.get("light")},
            "model": "offline" if sim.offline else cfg.model,
        }

    def broadcast(self, paused=False):
        """À appeler après chaque tick (thread principal)."""
        sim, w = self.sim, self.sim.world
        with self.lock:
            self.clients = [c for c in self.clients if c.alive]
            clients = list(self.clients)
        if not clients:
            w.dirty.clear()
            self._ev_sent = sim.event_total
            return
        new = [c for c in clients if not c.ready]
        if new:
            data = self._encode(self.init_message())
            for c in new:
                c.push(data)
                c.ready = True
        day, hour, phase, _ = sim.clock()
        cells = [self._cell(x, y) for (x, y) in w.dirty]
        w.dirty.clear()
        sites = self._sites()
        n_ev = sim.event_total - self._ev_sent
        events = [txt for _t, txt in list(sim.events)[-n_ev:]] if n_ev > 0 else []
        self._ev_sent = sim.event_total
        msg = {
            "type": "tick", "tick": sim.tick, "day": day, "hour": hour, "night": phase == "night",
            "dark": round(sim.darkness(), 3), "tps": sim.cfg.ticks_per_second, "paused": paused,
            "agents": [self._agent(a) for a in sim.agents.values() if a.alive or a.death_cause],
            "animals": [self._animal(a) for a in sim.animals.animals.values()],
            "cells": cells, "events": events,
            "llm": dict(sim.llm.stats) if sim.llm else None,
        }
        if sites != self._last_sites:
            msg["sites"] = sites
            self._last_sites = sites
        if len(sim.agents) != self._people_n:  # naissance : nouveaux habitants à créer côté 3D
            msg["people"] = [self._agent_static(a) for a in sim.agents.values()]
            self._people_n = len(sim.agents)
        data = self._encode(msg)
        for c in clients:
            if c.ready:
                c.push(data)
