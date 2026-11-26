"""Affichage pygame : carte vue de dessus + panneau d'information."""
import textwrap
import time

import numpy as np
import pygame

from . import items as I
from . import world as W

TS = 8  # taille de case de la texture de terrain mise en cache

GROUND_COLORS = {
    W.WATER: (52, 110, 190), W.SAND: (222, 205, 150), W.GRASS: (96, 160, 72), W.DIRT: (130, 104, 70),
    W.FARMLAND: (100, 70, 40), W.STONE_FLOOR: (128, 126, 120), W.GRAVEL_GROUND: (150, 145, 140),
}
FEATURE_COLORS = {
    W.TREE: (30, 95, 40), W.BUSH: (55, 120, 50), W.TALL_GRASS: (120, 180, 85), W.ROCK: (105, 105, 108),
    W.COAL: (40, 40, 40), W.IRON: (205, 160, 130), W.GOLD: (240, 200, 60), W.DIAMOND: (90, 230, 230),
    W.CLAY: (160, 165, 185), W.MUSHROOM: (200, 60, 50), W.GRAVEL: (140, 135, 130), W.SAPLING: (80, 170, 60),
}
CROP_COLORS = [(120, 150, 60), (150, 175, 60), (190, 190, 60), (230, 200, 70)]

PANEL_W = 380
BG = (24, 26, 32)
FG = (225, 228, 235)
DIM = (140, 145, 155)
ACCENT = (255, 200, 90)


class App:
    def __init__(self, sim):
        self.sim = sim
        pygame.init()
        pygame.display.set_caption("LifeSim — simulation de vie pilotée par LLM")
        info = pygame.display.Info()
        self.W = min(1600, max(1100, info.current_w - 80))
        self.H = min(980, max(700, info.current_h - 120))
        self.screen = pygame.display.set_mode((self.W, self.H), pygame.RESIZABLE)
        self.font = pygame.font.SysFont("dejavusans,arial,liberationsans", 13)
        self.font_b = pygame.font.SysFont("dejavusans,arial,liberationsans", 14, bold=True)
        self.font_s = pygame.font.SysFont("dejavusans,arial,liberationsans", 11)
        self.clock = pygame.time.Clock()
        w = sim.world
        self.zoom = 8.0
        self.cam_x = w.w / 2 - (self.W - PANEL_W) / self.zoom / 2
        self.cam_y = w.h / 2 - self.H / self.zoom / 2
        self.speed = 1.0
        self.paused = False
        self.selected = None
        self.follow = False
        self.show_roofs = True
        self.show_help = False
        self.drag = None
        self.terrain = None
        self.terrain_version = -1
        self.terrain_time = 0
        self.acc = 0.0
        self.panel_scroll = 0
        self.agent_rows = []

    # ------------------------------------------------------------------ terrain
    def build_terrain(self):
        w = self.sim.world
        g = w.ground
        rgb = np.zeros((w.h, w.w, 3), dtype=np.uint8)
        for k, c in GROUND_COLORS.items():
            rgb[g == k] = c
        # légère variation pour un rendu moins plat
        noise = ((np.arange(w.w)[None, :] * 7 + np.arange(w.h)[:, None] * 13) % 5 - 2) * 3
        rgb = np.clip(rgb.astype(np.int16) + noise[..., None], 0, 255).astype(np.uint8)
        big = np.repeat(np.repeat(rgb, TS, axis=0), TS, axis=1)
        surf = pygame.surfarray.make_surface(big.swapaxes(0, 1))
        f = w.feature
        ys, xs = np.nonzero(f)
        for x, y in zip(xs.tolist(), ys.tolist()):
            fid = int(f[y, x])
            col = FEATURE_COLORS.get(fid)
            if col is None:
                continue
            px, py = x * TS, y * TS
            if fid == W.TREE:
                pygame.draw.circle(surf, col, (px + TS // 2, py + TS // 2), TS // 2)
                pygame.draw.circle(surf, (45, 120, 50), (px + TS // 2 - 1, py + TS // 2 - 1), TS // 4)
            elif fid in (W.ROCK, W.COAL, W.IRON, W.GOLD, W.DIAMOND):
                pygame.draw.rect(surf, (105, 105, 108), (px, py, TS, TS))
                if fid != W.ROCK:
                    pygame.draw.rect(surf, col, (px + 2, py + 2, 2, 2))
                    pygame.draw.rect(surf, col, (px + 5, py + 4, 2, 2))
                pygame.draw.line(surf, (85, 85, 88), (px, py + TS - 1), (px + TS - 1, py + TS - 1))
            elif fid == W.BUSH:
                pygame.draw.circle(surf, col, (px + TS // 2, py + TS // 2), TS // 2 - 1)
                if w.amount[y, x] > 0:
                    pygame.draw.circle(surf, (200, 40, 80), (px + 3, py + 3), 1)
                    pygame.draw.circle(surf, (200, 40, 80), (px + 5, py + 5), 1)
            elif fid == W.TALL_GRASS:
                pygame.draw.line(surf, col, (px + 2, py + TS - 1), (px + 2, py + 2))
                pygame.draw.line(surf, col, (px + 5, py + TS - 1), (px + 5, py + 3))
            elif fid == W.SAPLING:
                pygame.draw.circle(surf, col, (px + TS // 2, py + TS // 2), 2)
            else:
                pygame.draw.rect(surf, col, (px + 2, py + 2, TS - 4, TS - 4))
        for (x, y), c in w.crops.items():
            col = CROP_COLORS[min(3, c["stage"])]
            for i in range(3):
                pygame.draw.line(surf, col, (x * TS + 1 + i * 3, y * TS + TS - 1),
                                 (x * TS + 1 + i * 3, y * TS + TS - 2 - c["stage"] * 2))
        for (x, y), b in w.blocks.items():
            spec = I.BLOCKS[b.type]
            col = spec["color"]
            px, py = x * TS, y * TS
            if b.type in ("fence", "fence_gate"):
                pygame.draw.rect(surf, col, (px + 3, py, 2, TS))
                pygame.draw.rect(surf, col, (px, py + 3, TS, 2))
                if b.type == "fence_gate":
                    pygame.draw.rect(surf, (230, 200, 120), (px + 1, py + 1, TS - 2, TS - 2), 1)
            elif b.type in ("torch",):
                pygame.draw.circle(surf, col, (px + TS // 2, py + TS // 2), 2)
            elif b.type in ("door", "iron_door"):
                pygame.draw.rect(surf, col, (px + 1, py, TS - 2, TS))
                pygame.draw.circle(surf, (240, 220, 120), (px + TS - 3, py + TS // 2), 1)
            elif b.type == "bed":
                pygame.draw.rect(surf, col, (px + 1, py + 1, TS - 2, TS - 2))
                pygame.draw.rect(surf, (240, 240, 240), (px + 1, py + 1, TS - 2, 3))
            elif b.type == "campfire":
                pygame.draw.rect(surf, (90, 60, 30), (px + 1, py + 4, TS - 2, 3))
                pygame.draw.circle(surf, col, (px + TS // 2, py + 3), 3)
            else:
                pygame.draw.rect(surf, col, (px, py, TS, TS))
                pygame.draw.rect(surf, tuple(max(0, v - 35) for v in col), (px, py, TS, TS), 1)
                if b.type in ("crafting_table", "furnace", "chest", "anvil"):
                    pygame.draw.rect(surf, (20, 20, 20), (px + 2, py + 2, TS - 4, TS - 4), 1)
        for pos, c in w.ground_items.items():
            if c:
                pygame.draw.rect(surf, (250, 250, 120), (pos[0] * TS + 3, pos[1] * TS + 3, 2, 2))
        self.terrain = surf
        self.roof_layer = None
        if self.show_roofs and w.roofs:
            rl = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            for (x, y), mat in w.roofs.items():
                col = I.BLOCKS.get(mat, {}).get("color", (150, 100, 60))
                col = tuple(int(v * 0.75) for v in col)
                pygame.draw.rect(rl, (*col, 215), (x * TS, y * TS, TS, TS))
                pygame.draw.line(rl, (*tuple(max(0, v - 30) for v in col), 230),
                                 (x * TS, y * TS + TS // 2), (x * TS + TS - 1, y * TS + TS // 2))
            self.roof_layer = rl
        self.terrain_version = w.version
        self.terrain_time = time.time()

    # ------------------------------------------------------------------ coordonnées
    def map_w(self):
        return self.screen.get_width() - PANEL_W

    def to_screen(self, x, y):
        return ((x - self.cam_x) * self.zoom, (y - self.cam_y) * self.zoom)

    def to_world(self, sx, sy):
        return (sx / self.zoom + self.cam_x, sy / self.zoom + self.cam_y)

    def clamp_cam(self):
        w = self.sim.world
        vw = self.map_w() / self.zoom
        vh = self.screen.get_height() / self.zoom
        self.cam_x = max(-vw * 0.3, min(w.w - vw * 0.7, self.cam_x))
        self.cam_y = max(-vh * 0.3, min(w.h - vh * 0.7, self.cam_y))

    # ------------------------------------------------------------------ boucle
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(30) / 1000.0
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                else:
                    self.handle(ev)
            if getattr(self.sim, "save_path", None) and time.time() - self.sim.last_save_time > 300:
                self.save()
            if not self.paused:
                self.acc += dt * self.sim.cfg.ticks_per_second * self.speed
                n = int(self.acc)
                self.acc -= n
                t0 = time.time()
                for _ in range(min(n, 200)):
                    self.sim.step()
                    if time.time() - t0 > 0.09:
                        self.acc = 0
                        break
            if self.follow and self.selected and self.selected.alive:
                self.cam_x = self.selected.x - self.map_w() / self.zoom / 2
                self.cam_y = self.selected.y - self.screen.get_height() / self.zoom / 2
            self.draw()
        pygame.quit()

    def save(self):
        from . import persistence
        if not getattr(self.sim, "save_path", None):
            return
        try:
            persistence.save(self.sim, self.sim.save_path)
            self.sim.event("💾 Partie sauvegardée.")
        except Exception as e:
            self.sim.event(f"⚠ Sauvegarde impossible : {e}")

    def handle(self, ev):
        if ev.type == pygame.KEYDOWN:
            k = ev.key
            if k == pygame.K_F5:
                self.save()
            elif k == pygame.K_SPACE:
                self.paused = not self.paused
            elif k in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
                self.speed = min(32.0, self.speed * 2)
            elif k in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_6):
                self.speed = max(0.25, self.speed / 2)
            elif k == pygame.K_r:
                self.show_roofs = not self.show_roofs
                self.terrain_version = -1
            elif k == pygame.K_f:
                self.follow = not self.follow
            elif k == pygame.K_h:
                self.show_help = not self.show_help
            elif k == pygame.K_ESCAPE:
                self.selected = None
                self.follow = False
            elif k == pygame.K_TAB:
                alive = self.sim.living_agents()
                if alive:
                    if self.selected in alive:
                        i = (alive.index(self.selected) + 1) % len(alive)
                    else:
                        i = 0
                    self.selected = alive[i]
                    self.center_on(self.selected)
            elif k in (pygame.K_LEFT, pygame.K_q):
                self.cam_x -= 40 / self.zoom
            elif k == pygame.K_RIGHT or k == pygame.K_d:
                self.cam_x += 40 / self.zoom
            elif k in (pygame.K_UP, pygame.K_z):
                self.cam_y -= 40 / self.zoom
            elif k == pygame.K_DOWN or k == pygame.K_s:
                self.cam_y += 40 / self.zoom
        elif ev.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if mx < self.map_w():
                wx, wy = self.to_world(mx, my)
                self.zoom = max(3.0, min(40.0, self.zoom * (1.2 if ev.y > 0 else 1 / 1.2)))
                self.cam_x = wx - mx / self.zoom
                self.cam_y = wy - my / self.zoom
            else:
                self.panel_scroll = max(0, self.panel_scroll - ev.y * 30)
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button in (2, 3) or (ev.button == 1 and pygame.key.get_mods() & pygame.KMOD_SHIFT):
                self.drag = (ev.pos, self.cam_x, self.cam_y)
            elif ev.button == 1:
                mx, my = ev.pos
                if mx < self.map_w():
                    self.select_at(mx, my)
                else:
                    for rect, ag in self.agent_rows:
                        if rect.collidepoint(mx, my):
                            self.selected = ag
                            self.center_on(ag)
                            self.panel_scroll = 0
        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button in (1, 2, 3):
                self.drag = None
        elif ev.type == pygame.MOUSEMOTION and self.drag:
            (sx, sy), cx, cy = self.drag
            self.cam_x = cx - (ev.pos[0] - sx) / self.zoom
            self.cam_y = cy - (ev.pos[1] - sy) / self.zoom
            self.follow = False
        self.clamp_cam()

    def center_on(self, ag):
        self.cam_x = ag.x - self.map_w() / self.zoom / 2
        self.cam_y = ag.y - self.screen.get_height() / self.zoom / 2
        self.clamp_cam()

    def select_at(self, mx, my):
        wx, wy = self.to_world(mx, my)
        best, bd = None, 2.0
        for ag in self.sim.living_agents():
            d = abs(ag.x + 0.5 - wx) + abs(ag.y + 0.5 - wy)
            if d < bd:
                best, bd = ag, d
        self.selected = best
        self.panel_scroll = 0

    # ------------------------------------------------------------------ dessin
    def draw(self):
        sim = self.sim
        scr = self.screen
        scr.fill((10, 12, 16))
        if self.terrain is None or (sim.world.version != self.terrain_version and time.time() - self.terrain_time > 0.6):
            self.build_terrain()
        mw, mh = self.map_w(), scr.get_height()
        z = self.zoom
        # portion visible de la texture
        x0, y0 = int(max(0, self.cam_x)), int(max(0, self.cam_y))
        x1 = int(min(sim.world.w, self.cam_x + mw / z + 2))
        y1 = int(min(sim.world.h, self.cam_y + mh / z + 2))
        if x1 > x0 and y1 > y0:
            rect = pygame.Rect(x0 * TS, y0 * TS, (x1 - x0) * TS, (y1 - y0) * TS)
            size = (int((x1 - x0) * z), int((y1 - y0) * z))
            dest = self.to_screen(x0, y0)
            sub = pygame.transform.scale(self.terrain.subsurface(rect), size)
            scr.blit(sub, dest)
            if self.show_roofs and self.roof_layer is not None:
                scr.blit(pygame.transform.scale(self.roof_layer.subsurface(rect), size), dest)

        # animaux
        for a in sim.animals.animals.values():
            if not (x0 - 1 <= a.x <= x1 and y0 - 1 <= a.y <= y1):
                continue
            sx, sy = self.to_screen(a.x + 0.5, a.y + 0.5)
            r = max(2, int(z * (0.32 if a.adult else 0.2)))
            col = a.spec["color"]
            if a.species == "wolf":
                pygame.draw.polygon(scr, col, [(sx, sy - r), (sx + r, sy + r), (sx - r, sy + r)])
                if a.owner is not None:
                    owner = sim.agents.get(a.owner)
                    if owner:
                        pygame.draw.polygon(scr, owner.color, [(sx, sy - r), (sx + r, sy + r), (sx - r, sy + r)], 2)
            else:
                pygame.draw.rect(scr, col, (sx - r, sy - r * 0.8, 2 * r, 1.6 * r), border_radius=max(1, r // 2))
                pygame.draw.rect(scr, (30, 30, 30), (sx - r, sy - r * 0.8, 2 * r, 1.6 * r), 1, border_radius=max(1, r // 2))
            if a.leashed_to is not None:
                ag = sim.agents.get(a.leashed_to)
                if ag:
                    pygame.draw.line(scr, (200, 170, 110), (sx, sy), self.to_screen(ag.x + 0.5, ag.y + 0.5), 1)

        # habitants
        for ag in sim.living_agents():
            if not (x0 - 2 <= ag.x <= x1 + 1 and y0 - 2 <= ag.y <= y1 + 1):
                continue
            sx, sy = self.to_screen(ag.x + 0.5, ag.y + 0.5)
            r = max(3, int(z * 0.45))
            pygame.draw.circle(scr, ag.color, (sx, sy), r)
            pygame.draw.circle(scr, (0, 0, 0), (sx, sy), r, 2 if ag is self.selected else 1)
            if ag is self.selected:
                pygame.draw.circle(scr, (255, 255, 255), (sx, sy), r + 4, 2)
            if ag.weapon()[0]:
                pygame.draw.line(scr, (220, 220, 230), (sx + r * 0.6, sy - r * 0.2), (sx + r * 1.4, sy - r * 1.1), 2)
            if ag.combat_target is not None:
                pygame.draw.circle(scr, (255, 40, 40), (sx, sy), r + 2, 1)
            # barre de vie
            if z >= 6:
                bw = max(10, int(z * 1.0))
                pygame.draw.rect(scr, (60, 0, 0), (sx - bw / 2, sy - r - 5, bw, 3))
                pygame.draw.rect(scr, (80, 220, 80), (sx - bw / 2, sy - r - 5, bw * max(0, ag.hp) / sim.cfg.max_hp, 3))
            if z >= 11 or ag is self.selected:
                lbl = self.font_s.render(ag.name, True, (255, 255, 255))
                scr.blit(lbl, (sx - lbl.get_width() / 2, sy + r + 1))
            if ag.sleeping:
                scr.blit(self.font_s.render("z", True, (200, 200, 255)), (sx + r, sy - r - 10))
            if ag.llm_pending and z >= 8:
                pygame.draw.circle(scr, (255, 255, 255), (sx + r, sy - r), 3)
                pygame.draw.circle(scr, (90, 160, 255), (sx + r, sy - r), 2)

        # bulles de dialogue
        for ag in sim.living_agents():
            if ag.speech and x0 - 5 <= ag.x <= x1 + 5 and y0 - 5 <= ag.y <= y1 + 5:
                sx, sy = self.to_screen(ag.x + 0.5, ag.y)
                self.bubble(ag.speech[0], sx, sy - 10)

        # nuit
        d = sim.darkness()
        if d > 0:
            dark = pygame.Surface((mw, mh), pygame.SRCALPHA)
            dark.fill((5, 10, 40, int(150 * d)))
            for (lx, ly) in sim.world.light_sources:
                if x0 - 6 <= lx <= x1 + 6 and y0 - 6 <= ly <= y1 + 6:
                    b = sim.world.blocks.get((lx, ly))
                    if b is None:
                        continue
                    rad = I.BLOCKS[b.type].get("light", 0)
                    sx, sy = self.to_screen(lx + 0.5, ly + 0.5)
                    pygame.draw.circle(dark, (40, 25, 0, int(60 * d)), (sx, sy), (rad + 0.5) * z)
            scr.blit(dark, (0, 0))

        self.draw_panel()
        if self.show_help:
            self.draw_help()
        pygame.display.flip()

    def bubble(self, text, sx, sy):
        lines = textwrap.wrap(text, 34)[:4]
        if not lines:
            return
        surfs = [self.font_s.render(l, True, (20, 20, 20)) for l in lines]
        w = max(s.get_width() for s in surfs) + 10
        h = sum(s.get_height() for s in surfs) + 6
        x, y = sx - w / 2, sy - h
        pygame.draw.rect(self.screen, (250, 250, 240), (x, y, w, h), border_radius=5)
        pygame.draw.rect(self.screen, (60, 60, 60), (x, y, w, h), 1, border_radius=5)
        yy = y + 3
        for s in surfs:
            self.screen.blit(s, (x + 5, yy))
            yy += s.get_height()

    # ------------------------------------------------------------------ panneau
    def text(self, txt, x, y, col=FG, font=None, width=None):
        font = font or self.font
        if width:
            maxc = max(10, int(width / (font.size("m")[0] * 0.82)))
            lines = []
            for para in str(txt).split("\n"):
                lines += textwrap.wrap(para, maxc) or [""]
        else:
            lines = [str(txt)]
        for l in lines:
            if 0 <= y < self.screen.get_height():
                self.screen.blit(font.render(l, True, col), (x, y))
            y += font.get_linesize()
        return y

    def bar(self, x, y, w, frac, col, label):
        pygame.draw.rect(self.screen, (55, 58, 66), (x, y, w, 12), border_radius=3)
        pygame.draw.rect(self.screen, col, (x, y, w * max(0, min(1, frac)), 12), border_radius=3)
        self.screen.blit(self.font_s.render(label, True, (10, 10, 10)), (x + 4, y))

    def draw_panel(self):
        sim = self.sim
        scr = self.screen
        px = self.map_w()
        H = scr.get_height()
        pygame.draw.rect(scr, BG, (px, 0, PANEL_W, H))
        pygame.draw.line(scr, (60, 64, 75), (px, 0), (px, H))
        x = px + 12
        wdt = PANEL_W - 24
        day, hour, phase, _ = sim.clock()
        y = 8
        y = self.text(f"Jour {day} — {hour} ({'nuit' if phase == 'night' else 'jour'})", x, y, ACCENT, self.font_b)
        alive = sim.living_agents()
        status = "PAUSE" if self.paused else f"x{self.speed:g}"
        y = self.text(f"Tick {sim.tick}  |  vitesse {status}  |  habitants {len(alive)}", x, y, DIM)
        if sim.llm:
            st = sim.llm.stats
            y = self.text(f"LLM {sim.cfg.model}", x, y, DIM, self.font_s)
            y = self.text(f"appels {st['calls']}  ok {st['ok']}  err {st['errors']}  en cours {st['in_flight']}  "
                          f"{st['last_latency']:.1f}s", x, y, DIM, self.font_s)
            y = self.text(f"tokens {st['prompt_tokens'] + st['completion_tokens']:,}  coût ${st['cost']:.4f}",
                          x, y, DIM, self.font_s)
            if sim.llm.last_error and st["errors"]:
                y = self.text("dernière erreur : " + sim.llm.last_error[:140], x, y, (255, 120, 120), self.font_s, wdt)
        else:
            y = self.text("Mode hors-ligne (cerveau heuristique)", x, y, (255, 160, 100), self.font_s)
        y += 6
        pygame.draw.line(scr, (60, 64, 75), (x, y), (x + wdt, y))
        y += 6
        top_events = y
        ag = self.selected if self.selected and self.selected.alive else None
        if self.selected and not self.selected.alive:
            y = self.text(f"{self.selected.name} est mort(e) : {self.selected.death_cause}", x, y, (255, 110, 110))
        events_h = 210
        clip = pygame.Rect(px, y, PANEL_W, H - y - events_h)
        scr.set_clip(clip)
        y0 = y - self.panel_scroll
        if ag:
            y = self.draw_agent(ag, x, y0, wdt)
        else:
            y = self.draw_agent_list(x, y0, wdt)
        scr.set_clip(None)
        # événements
        ey = H - events_h
        pygame.draw.rect(scr, (18, 20, 25), (px + 1, ey, PANEL_W, events_h))
        pygame.draw.line(scr, (60, 64, 75), (px, ey), (px + PANEL_W, ey))
        ey = self.text("Événements", x, ey + 4, ACCENT, self.font_b)
        lines = []
        for t, txt in list(sim.events)[-40:]:
            lines += [(t, l) for l in textwrap.wrap(txt, 58)]
        n = (events_h - 40) // self.font_s.get_linesize()
        for t, l in lines[-n:]:
            ey = self.text(l, x, ey, (200, 205, 215), self.font_s)
        self.text("H : aide  |  Espace : pause  |  +/- : vitesse", x, H - 16, DIM, self.font_s)

    def draw_agent_list(self, x, y, wdt):
        self.agent_rows = []
        y = self.text("Habitants (cliquer pour suivre)", x, y, ACCENT, self.font_b)
        for ag in self.sim.living_agents():
            r = pygame.Rect(x - 4, y, wdt + 8, 17)
            if r.collidepoint(pygame.mouse.get_pos()):
                pygame.draw.rect(self.screen, (45, 48, 58), r)
            pygame.draw.circle(self.screen, ag.color, (x + 5, y + 8), 5)
            act = self.sim.describe_activity(ag)
            txt = f"{ag.name:<10} PV {ag.hp:4.1f}  faim {ag.hunger:3.0f}  {act}"
            self.text(txt[:60], x + 14, y + 1, FG, self.font_s)
            self.agent_rows.append((r, ag))
            y += 17
        return y

    def draw_agent(self, ag, x, y, wdt):
        sim = self.sim
        self.agent_rows = []
        pygame.draw.circle(self.screen, ag.color, (x + 7, y + 9), 7)
        y = self.text(f"{ag.name}  ({ag.x},{ag.y})", x + 20, y, ACCENT, self.font_b)
        if ag.parents:
            y = self.text("enfant de " + " & ".join(sim.agents[p].name for p in ag.parents), x, y, DIM, self.font_s)
        y += 2
        self.bar(x, y, wdt // 2 - 4, ag.hp / sim.cfg.max_hp, (90, 210, 90), f"PV {ag.hp:.1f}")
        self.bar(x + wdt // 2 + 4, y, wdt // 2 - 4, ag.hunger / 100, (230, 170, 70), f"faim {ag.hunger:.0f}")
        y += 18
        wpn = ag.weapon()[0] or "poings"
        y = self.text(f"arme : {wpn}   armure : {ag.armor_name() or '-'}   tués : {ag.kills}", x, y, DIM, self.font_s)
        y = self.text(f"décisions LLM : {ag.decision_count}" + ("   (réflexion…)" if ag.llm_pending else ""),
                      x, y, DIM, self.font_s)
        y += 4
        y = self.text("Pensée", x, y, ACCENT, self.font_b)
        y = self.text(ag.thought or "…", x, y, FG, self.font, wdt)
        y += 4
        y = self.text("Plan", x, y, ACCENT, self.font_b)
        for i, st in enumerate(ag.plan):
            params = ", ".join(f"{k}={v}" for k, v in st.items() if k not in ("action", "_reflex"))
            mark = "✓" if i < ag.step_idx else ("▶" if i == ag.step_idx else "·")
            col = DIM if i < ag.step_idx else (FG if i > ag.step_idx else (140, 230, 140))
            y = self.text(f"{mark} {st['action']}({params})"[:200], x, y, col, self.font_s, wdt)
        if not ag.plan:
            y = self.text("(aucun)", x, y, DIM, self.font_s)
        if ag.routine:
            y = self.text(f"Routine ({ag.routine_cycles} cycles)" + ("  ▶ en cours" if ag.in_routine else ""),
                          x, y + 2, ACCENT, self.font_s)
            for st in ag.routine:
                params = ", ".join(f"{k}={v}" for k, v in st.items() if k != "action")
                y = self.text(f"↻ {st['action']}({params})"[:200], x, y, DIM, self.font_s, wdt)
        if ag.step_results:
            for r in ag.step_results[-3:]:
                y = self.text(r[:200], x, y, (255, 140, 140) if r.startswith("FAIL") else DIM, self.font_s, wdt)
        y += 4
        y = self.text("Inventaire", x, y, ACCENT, self.font_b)
        y = self.text(ag.inv_text(), x, y, FG, self.font_s, wdt)
        if ag.notes:
            y += 4
            y = self.text("Notes", x, y, ACCENT, self.font_b)
            y = self.text(ag.notes, x, y, FG, self.font_s, wdt)
        mine = [s for s in sim.structures.values() if s.owner == ag.id]
        if mine:
            y += 4
            y = self.text("Constructions", x, y, ACCENT, self.font_b)
            for s in mine[-5:]:
                y = self.text(s.summary(), x, y, FG, self.font_s, wdt)
        refl = [m[1] for m in ag.longmem if m[4] == "reflection"][-3:]
        if refl:
            y += 4
            y = self.text("Réflexions", x, y, ACCENT, self.font_b)
            for r in refl:
                y = self.text(f"« {r} »", x, y, FG, self.font_s, wdt)
        rels = sorted(((oid, r) for oid, r in ag.rel.items() if r["n"] or r["bond"] or abs(r["aff"]) >= 3),
                      key=lambda kv: -(abs(kv[1]["aff"]) + (60 if kv[1]["bond"] else 0)))[:4]
        if rels:
            y += 4
            y = self.text("Liens", x, y, ACCENT, self.font_b)
            for oid, r in rels:
                o = sim.agents.get(oid)
                if o is None:
                    continue
                col = (140, 220, 140) if r["aff"] >= 8 else (255, 140, 120) if r["aff"] <= -8 else DIM
                txt = f"{o.name} {r['aff']:+.0f}" + (f" ({r['bond']})" if r["bond"] else "") + \
                      (f" — {r['opinion']}" if r["opinion"] else "")
                y = self.text(txt[:160], x, y, col, self.font_s, wdt)
        y += 4
        y = self.text("Mémoire", x, y, ACCENT, self.font_b)
        for t, m in list(ag.memory)[-8:]:
            y = self.text(f"[{t}] {m}", x, y, DIM, self.font_s, wdt)
        if ag.last_error:
            y = self.text("⚠ " + ag.last_error, x, y, (255, 120, 120), self.font_s, wdt)
        return y

    def draw_help(self):
        lines = [
            "Commandes",
            "Clic gauche : sélectionner un habitant      Échap : désélectionner",
            "Clic droit / molette-clic / Maj+clic glisser : déplacer la carte",
            "Molette (carte) : zoom    Molette (panneau) : défiler",
            "Flèches / ZQSD : déplacer      Tab : habitant suivant      F : suivre",
            "Espace : pause      + / - : vitesse      R : afficher/masquer les toits",
            "F5 : sauvegarder (auto toutes les 5 min et à la fermeture ; reprendre avec --load)",
            "",
            "Légende",
            "Cercle coloré = habitant (trait blanc = arme, cercle rouge = combat, point bleu = réfléchit)",
            "Carré blanc = mouton, brun = vache, rose = cochon, jaune = poule, triangle gris = loup",
            "Gris = roche (points : charbon noir, fer beige, or jaune, diamant cyan)",
            "Brun foncé + traits = champ de blé (jaune = mûr)",
        ]
        w = 640
        h = len(lines) * 20 + 20
        x = (self.map_w() - w) / 2
        y = 40
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((15, 17, 22, 230))
        self.screen.blit(s, (x, y))
        yy = y + 10
        for i, l in enumerate(lines):
            col = ACCENT if l in ("Commandes", "Légende") else FG
            self.screen.blit(self.font.render(l, True, col), (x + 14, yy))
            yy += 20
