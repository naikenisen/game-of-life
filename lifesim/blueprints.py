"""Plans de construction : transforment une intention (« une maison 5x5 en pierre ici »)
en une liste ordonnée de cases à poser. La construction elle-même est faite par algo."""
from dataclasses import dataclass, field

from . import items as I
from . import world as W

WALL_MATERIALS = ["planks", "cobblestone", "brick", "log", "glass", "iron_block", "fence"]
MAX_CELLS = 220


@dataclass
class Site:
    id: int
    owner: int
    kind: str
    x: int
    y: int
    w: int
    h: int
    label: str
    cells: list                       # [(x, y, op, material)] op: block | roof | till | plant
    done: int = 0
    status: str = "planned"           # planned / in_progress / paused / complete / abandoned
    missing: dict = field(default_factory=dict)
    created: int = 0

    @property
    def remaining(self):
        return self.cells[self.done:]

    def needs(self):
        need = {}
        for (_, _, op, mat) in self.remaining:
            if op in ("block", "roof"):
                need[mat] = need.get(mat, 0) + 1
            elif op == "plant":
                need["wheat_seeds"] = need.get("wheat_seeds", 0) + 1
        return need

    def summary(self):
        s = f"#{self.id} {self.kind} '{self.label}' at ({self.x},{self.y}) size {self.w}x{self.h} [{self.status}"
        if self.status not in ("complete",):
            s += f", {self.done}/{len(self.cells)} done"
            n = self.needs()
            if n:
                s += ", still needs " + ", ".join(f"{v} {k}" for k, v in n.items())
        return s + "]"


class BlueprintError(Exception):
    pass


def _rect_perimeter(x, y, w, h):
    cells = []
    for dx in range(w):
        cells.append((x + dx, y))
    for dy in range(1, h):
        cells.append((x + w - 1, y + dy))
    for dx in range(w - 2, -1, -1):
        cells.append((x + dx, y + h - 1))
    for dy in range(h - 2, 0, -1):
        cells.append((x, y + dy))
    return cells


def _door_pos(x, y, w, h, side):
    side = (side or "south").lower()
    if side.startswith("n"):
        return (x + w // 2, y)
    if side.startswith("e"):
        return (x + w - 1, y + h // 2)
    if side.startswith("w"):
        return (x, y + h // 2)
    return (x + w // 2, y + h - 1)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _int(p, k, default):
    try:
        return int(p.get(k, default))
    except (TypeError, ValueError):
        return default


def make_cells(p):
    """p = paramètres de l'action build. Renvoie (kind, x, y, w, h, cells)."""
    kind = str(p.get("structure", p.get("type", "house"))).lower()
    x, y = _int(p, "x", 0), _int(p, "y", 0)
    cells = []

    if kind in ("house", "hut", "building", "shelter", "room"):
        w = _clamp(_int(p, "w", 5), 3, 14)
        h = _clamp(_int(p, "h", 5), 3, 14)
        mat = p.get("material", "planks")
        if mat not in WALL_MATERIALS:
            raise BlueprintError(f"invalid wall material '{mat}', use one of {WALL_MATERIALS}")
        door_type = p.get("door", "door")
        if door_type not in ("door", "iron_door", "fence_gate", "none", None):
            door_type = "door"
        dpos = _door_pos(x, y, w, h, p.get("door_side"))
        for c in _rect_perimeter(x, y, w, h):
            if c == dpos and door_type not in ("none", None):
                continue
            cells.append((c[0], c[1], "block", mat))
        if door_type not in ("none", None):
            cells.append((dpos[0], dpos[1], "block", door_type))
        roof = p.get("roof", mat if mat in I.ROOF_MATERIALS else "planks")
        if isinstance(roof, str) and roof.startswith("roof:"):
            roof = roof[5:]
        if roof in (False, None, "", "no", "false"):
            roof = "none"
        if roof and roof != "none":
            if roof not in I.ROOF_MATERIALS:
                raise BlueprintError(f"invalid roof material '{roof}', use one of {I.ROOF_MATERIALS}")
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    cells.append((xx, yy, "roof", roof))
        return "house", x, y, w, h, cells

    if kind in ("enclosure", "pen", "fence", "corral", "paddock"):
        w = _clamp(_int(p, "w", 7), 3, 24)
        h = _clamp(_int(p, "h", 7), 3, 24)
        mat = p.get("material", "fence")
        if mat not in WALL_MATERIALS:
            mat = "fence"
        gate = p.get("door", "fence_gate")
        if gate not in ("door", "iron_door", "fence_gate", "none"):
            gate = "fence_gate"
        gpos = _door_pos(x, y, w, h, p.get("door_side"))
        for c in _rect_perimeter(x, y, w, h):
            if c == gpos and gate != "none":
                continue
            cells.append((c[0], c[1], "block", mat))
        if gate != "none":
            cells.append((gpos[0], gpos[1], "block", gate))
        return "enclosure", x, y, w, h, cells

    if kind in ("wall", "line", "barrier"):
        x2, y2 = _int(p, "x2", x), _int(p, "y2", y)
        mat = p.get("material", "cobblestone")
        if mat not in WALL_MATERIALS:
            raise BlueprintError(f"invalid wall material '{mat}'")
        n = max(abs(x2 - x), abs(y2 - y))
        if n > 60:
            raise BlueprintError("wall too long (max 60)")
        seen = set()
        for i in range(n + 1):
            t = i / n if n else 0
            c = (round(x + (x2 - x) * t), round(y + (y2 - y) * t))
            if c not in seen:
                seen.add(c)
                cells.append((c[0], c[1], "block", mat))
        return "wall", min(x, x2), min(y, y2), abs(x2 - x) + 1, abs(y2 - y) + 1, cells

    if kind in ("farm", "field", "crop_field"):
        w = _clamp(_int(p, "w", 5), 1, 16)
        h = _clamp(_int(p, "h", 5), 1, 16)
        plant = p.get("plant", True)
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                cells.append((xx, yy, "till", None))
        if plant not in (False, "none", "no"):
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    cells.append((xx, yy, "plant", "wheat_seeds"))
        return "farm", x, y, w, h, cells

    if kind == "roof":
        w = _clamp(_int(p, "w", 5), 1, 16)
        h = _clamp(_int(p, "h", 5), 1, 16)
        roof = str(p.get("material", "planks")).replace("roof:", "")
        if roof not in I.ROOF_MATERIALS:
            raise BlueprintError(f"invalid roof material '{roof}', use one of {I.ROOF_MATERIALS}")
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                cells.append((xx, yy, "roof", roof))
        return "roof", x, y, w, h, cells

    if kind in ("custom", "blocks"):
        raw = p.get("cells") or p.get("blocks") or []
        if not isinstance(raw, list) or not raw:
            raise BlueprintError("custom structure needs 'cells': [[dx,dy,block_or_roof:material], ...]")
        xs, ys = [], []
        for c in raw[:MAX_CELLS]:
            try:
                dx, dy, mat = int(c[0]), int(c[1]), str(c[2])
            except Exception:
                continue
            op = "block"
            if mat.startswith("roof:"):
                op, mat = "roof", mat[5:]
                if mat not in I.ROOF_MATERIALS:
                    continue
            elif mat == "farmland":
                op, mat = "till", None
            elif mat not in I.BLOCKS:
                raise BlueprintError(f"unknown block '{mat}'")
            cells.append((x + dx, y + dy, op, mat))
            xs.append(x + dx)
            ys.append(y + dy)
        if not cells:
            raise BlueprintError("no valid cells")
        # blocs d'abord, toits ensuite
        cells.sort(key=lambda c: c[2] == "roof")
        return "custom", min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, cells

    raise BlueprintError(f"unknown structure '{kind}' (house, enclosure, wall, farm, roof, custom)")


def validate(world, cells, owner):
    """Renvoie None si l'emplacement convient, sinon une raison."""
    for (x, y, op, _mat) in cells:
        if not world.in_bounds(x, y):
            return f"({x},{y}) is outside the map"
        if op == "roof":
            continue
        if world.ground[y, x] == W.WATER:
            return f"({x},{y}) is water"
        b = world.blocks.get((x, y))
        if b is not None and b.owner != owner:
            return f"({x},{y}) already has a {b.type} owned by someone else"
        if op in ("till", "plant") and world.ground[y, x] not in (W.GRASS, W.DIRT, W.FARMLAND):
            return f"({x},{y}) is not grass/dirt (cannot farm)"
    return None


def relocate(world, p, owner, max_shift=8):
    """Essaie l'emplacement demandé puis des décalages proches ; renvoie (params, cells, kind, bbox, note)."""
    base_x, base_y = _int(p, "x", 0), _int(p, "y", 0)
    shifts = [(0, 0)] + [(dx, dy) for r in range(1, max_shift + 1)
                         for dx in range(-r, r + 1) for dy in range(-r, r + 1) if max(abs(dx), abs(dy)) == r]
    first_err = None
    for dx, dy in shifts:
        q = dict(p)
        q["x"], q["y"] = base_x + dx, base_y + dy
        if "x2" in p:
            q["x2"] = _int(p, "x2", 0) + dx
            q["y2"] = _int(p, "y2", 0) + dy
        kind, x, y, w, h, cells = make_cells(q)
        err = validate(world, cells, owner)
        if err is None:
            note = "" if (dx, dy) == (0, 0) else f" (moved by {dx},{dy} because: {first_err})"
            return kind, x, y, w, h, cells, note
        if first_err is None:
            first_err = err
    raise BlueprintError(f"cannot build here: {first_err}")
