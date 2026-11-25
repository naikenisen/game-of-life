class_name Buildings
extends Node3D
## Tout ce que les habitants posent : murs (fins, raccordés comme dans les Sims),
## portes animées, toits à deux pans, parquets, meubles, feux, lumières.

const T := Assets.T
const WALL_H := 3.0
const TH := 0.4          # épaisseur des murs
const CH := 16

const WALLS := ["planks", "log", "cobblestone", "brick", "glass", "iron_block"]
const DOORS := ["door", "iron_door", "fence_gate"]
const FENCES := ["fence", "fence_gate"]
const LIGHT_BLOCKS := {"torch": [4.0, Color(1.0, 0.7, 0.35)], "campfire": [6.0, Color(1.0, 0.6, 0.25)],
	"furnace": [3.5, Color(1.0, 0.55, 0.2)], "lamp": [4.5, Color(1.0, 0.85, 0.6)]}

var terrain: Terrain
var blocks := {}       # Vector2i -> [type, owner]
var roofs := {}        # Vector2i -> material
var wall_chunks := {}  # Vector2i -> Node3D (murs/clôtures d'un bloc de cases)
var items := {}        # Vector2i -> Node3D (meubles, portes...)
var doors := {}        # Vector2i -> Node3D (pivot du battant)
var roof_root: Node3D
var roof_nodes := []   # [{node, rect:Rect2i, tiles}]
var floor_h := {}      # Vector2i -> hauteur du plancher
var lights := {}       # Vector2i -> [Vector3, rayon, couleur]
var dirty_walls := {}
var roofs_dirty := false
var roof_mode := "auto"   # on / off / auto
var hidden_roof_tiles := {}
var cut_center := Vector3.ZERO   # vue en coupe : toits cachés autour de ce point
var cut_radius := 0.0
var _mats := {}


func setup(t: Terrain, d: Dictionary) -> void:
	terrain = t
	roof_root = Node3D.new()
	roof_root.name = "Roofs"
	add_child(roof_root)
	for b in d["blocks"]:
		blocks[Vector2i(b[0], b[1])] = [b[2], b[3]]
	for r in d["roofs"]:
		roofs[Vector2i(r[0], r[1])] = r[2]
	for k in blocks:
		_mark_walls(k)
		_rebuild_item(k)
	roofs_dirty = true
	flush(1000)


func _mat(kind: String) -> Material:
	if _mats.has(kind):
		return _mats[kind]
	var m: Material
	match kind:
		"planks": m = Assets.pbr("planks", 0.45)
		"log": m = Assets.pbr("logs", 0.4)
		"cobblestone": m = Assets.pbr("stone_wall", 0.35)
		"brick": m = Assets.pbr("brick", 0.4)
		"plaster":
			m = Assets.pbr("plaster", 0.4).duplicate()
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
		"floor":
			m = Assets.pbr("floor", 0.45).duplicate()
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
		"thatch":
			m = Assets.pbr("thatch", 0.35).duplicate()
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
		"roof_tiles":
			m = Assets.pbr("roof_tiles", 0.35).duplicate()
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
		"carpet": m = Assets.pbr("carpet", 0.6)
		"fence":
			var f := Assets.pbr("planks", 0.8).duplicate()
			f.albedo_color = Color(0.85, 0.75, 0.6)
			m = f
		"glass":
			var g := StandardMaterial3D.new()
			g.albedo_color = Color(0.75, 0.9, 1.0, 0.25)
			g.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			g.roughness = 0.05
			g.metallic = 0.2
			m = g
		"iron_block": m = Assets.color_mat(Color(0.75, 0.76, 0.8), 0.0, 0.35)
		"chest":
			var c := Assets.pbr("planks", 1.2).duplicate()
			c.albedo_color = Color(0.95, 0.7, 0.45)
			m = c
		_: m = Assets.color_mat(Color(0.6, 0.5, 0.4))
	_mats[kind] = m
	return m


# ---------------------------------------------------------------- mises à jour
func update_cell(c: Array) -> void:
	var k := Vector2i(c[0], c[1])
	var bt: String = c[5]
	var old = blocks.get(k)
	if bt == "":
		blocks.erase(k)
	else:
		blocks[k] = [bt, c[6]]
	var roof: String = c[7]
	var old_roof = roofs.get(k, "")
	if roof == "":
		roofs.erase(k)
	else:
		roofs[k] = roof
	if old_roof != roof:
		roofs_dirty = true
	var changed: bool = (old == null) != (bt == "") or (old != null and bt != "" and old[0] != bt)
	if changed:
		_mark_walls(k)
		_rebuild_item(k)
		if roofs.has(k) or old_roof != "":
			roofs_dirty = true
		# les meubles voisins peuvent changer d'orientation
		for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			if blocks.has(k + d) and not _is_wallish(blocks[k + d][0]):
				_rebuild_item(k + d)


func _mark_walls(k: Vector2i) -> void:
	for d in [Vector2i(0, 0), Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
		var q: Vector2i = k + d
		dirty_walls[Vector2i(q.x / CH, q.y / CH)] = true


func flush(budget := 4) -> void:
	var n := 0
	for ck in dirty_walls.keys():
		_build_wall_chunk(ck)
		dirty_walls.erase(ck)
		n += 1
		if n >= budget:
			break
	if roofs_dirty:
		roofs_dirty = false
		_build_roofs()


func _is_wallish(t: String) -> bool:
	return t in WALLS or t in DOORS or t == "fence"


func _connects(a: String, b: String) -> bool:
	var af := a in FENCES
	var bf := b in FENCES
	if af or bf:
		return (af and bf) or (a == "fence_gate" or b == "fence_gate") and (_is_wallish(a) and _is_wallish(b))
	return _is_wallish(a) and _is_wallish(b)


func ground_y(x: int, y: int) -> float:
	return terrain.tile_height(x, y)


## Hauteur du sol (plancher de maison ou terrain) pour placer personnages et meubles.
func floor_at(x: int, y: int) -> float:
	var k := Vector2i(x, y)
	if floor_h.has(k):
		return floor_h[k]
	return terrain.tile_height(x, y)


# ---------------------------------------------------------------- murs et clôtures
func _build_wall_chunk(ck: Vector2i) -> void:
	if wall_chunks.has(ck):
		wall_chunks[ck].queue_free()
		wall_chunks.erase(ck)
	var tools := {}
	var x0 := ck.x * CH
	var y0 := ck.y * CH
	for y in range(y0, y0 + CH):
		for x in range(x0, x0 + CH):
			var k := Vector2i(x, y)
			if not blocks.has(k):
				continue
			var t: String = blocks[k][0]
			if not (t in WALLS or t == "fence" or t in DOORS):
				continue
			var base := ground_y(x, y) - 0.3
			var c := Vector3(x * T + T / 2, base, y * T + T / 2)
			var conn := []
			for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
				var nb = blocks.get(k + d)
				if nb != null and _connects(t, nb[0]):
					conn.append(d)
			if t == "fence" or t == "fence_gate":
				_fence(tools, c, conn, t == "fence_gate")
			elif t in DOORS:
				_door_frame(tools, c, conn, t)
			else:
				var mat_key := t
				var hh := WALL_H + 0.3
				if conn.is_empty():
					_box(tools, mat_key, c + Vector3(0, hh / 2, 0), Vector3(T * 0.55, hh, T * 0.55))
				else:
					_box(tools, mat_key, c + Vector3(0, hh / 2, 0), Vector3(TH, hh, TH))
					for d in conn:
						var off := Vector3(d.x, 0, d.y) * (T / 4)
						var size := Vector3(T / 2 if d.x != 0 else TH, hh, T / 2 if d.y != 0 else TH)
						if t == "glass":
							# vitre dans un cadre de bois
							_box(tools, "glass", c + off + Vector3(0, hh / 2 + 0.2, 0), Vector3(size.x, hh - 1.2, size.z) * Vector3(1, 1, 1) - Vector3(0 if d.x != 0 else 0.25, 0, 0 if d.y != 0 else 0.25))
							_box(tools, "planks", c + off + Vector3(0, 0.45, 0), Vector3(size.x, 0.9, size.z))
							_box(tools, "planks", c + off + Vector3(0, hh - 0.15, 0), Vector3(size.x, 0.3, size.z))
						else:
							_box(tools, mat_key, c + off + Vector3(0, hh / 2, 0), size)
	if tools.is_empty():
		return
	var node := Node3D.new()
	add_child(node)
	wall_chunks[ck] = node
	for mk in tools:
		var st: SurfaceTool = tools[mk]
		st.generate_tangents()
		var mi := MeshInstance3D.new()
		mi.mesh = st.commit()
		mi.material_override = _mat(mk)
		if mk == "glass":
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		node.add_child(mi)


func _fence(tools: Dictionary, c: Vector3, conn: Array, gate: bool) -> void:
	_box(tools, "fence", c + Vector3(0, 0.75, 0), Vector3(0.18, 1.5, 0.18))
	for d in conn:
		var off := Vector3(d.x, 0, d.y) * (T / 4)
		var along := Vector3(T / 2 if d.x != 0 else 0.08, 0.1, T / 2 if d.y != 0 else 0.08)
		if not gate:
			_box(tools, "fence", c + off + Vector3(0, 0.6, 0), along)
			_box(tools, "fence", c + off + Vector3(0, 1.05, 0), along)
	if gate:
		var axis_x := conn.is_empty() or conn.any(func(d): return d.x != 0)
		var along := Vector3(T * 0.9 if axis_x else 0.08, 0.12, 0.08 if axis_x else T * 0.9)
		_box(tools, "planks", c + Vector3(0, 0.55, 0), along)
		_box(tools, "planks", c + Vector3(0, 1.0, 0), along)


func _door_frame(tools: Dictionary, c: Vector3, conn: Array, t: String) -> void:
	if t == "fence_gate":
		_fence(tools, c, conn, true)
		return
	var mat := "planks"
	for d in conn:
		var nb = blocks.get(Vector2i(int((c.x - T / 2) / T) + d.x, int((c.z - T / 2) / T) + d.y))
		if nb != null and nb[0] in WALLS and nb[0] != "glass":
			mat = nb[0]
	var axis_x := conn.is_empty() or conn.any(func(d): return d.x != 0)
	var hh := WALL_H + 0.3
	# linteau + montants
	var span := Vector3(T, 0.7, TH) if axis_x else Vector3(TH, 0.7, T)
	_box(tools, mat, c + Vector3(0, hh - 0.35, 0), span)
	var side := Vector3(0.3, hh, TH) if axis_x else Vector3(TH, hh, 0.3)
	var so := Vector3(T / 2 - 0.15, 0, 0) if axis_x else Vector3(0, 0, T / 2 - 0.15)
	_box(tools, mat, c + so + Vector3(0, hh / 2, 0), side)
	_box(tools, mat, c - so + Vector3(0, hh / 2, 0), side)


func _box(tools: Dictionary, mat: String, center: Vector3, size: Vector3) -> void:
	if not tools.has(mat):
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		tools[mat] = st
	var s: SurfaceTool = tools[mat]
	var h := size / 2
	var p := [
		center + Vector3(-h.x, -h.y, -h.z), center + Vector3(h.x, -h.y, -h.z), center + Vector3(h.x, h.y, -h.z), center + Vector3(-h.x, h.y, -h.z),
		center + Vector3(-h.x, -h.y, h.z), center + Vector3(h.x, -h.y, h.z), center + Vector3(h.x, h.y, h.z), center + Vector3(-h.x, h.y, h.z)]
	var faces := [[0, 3, 2, 1, Vector3(0, 0, -1)], [4, 5, 6, 7, Vector3(0, 0, 1)], [0, 4, 7, 3, Vector3(-1, 0, 0)],
		[1, 2, 6, 5, Vector3(1, 0, 0)], [3, 7, 6, 2, Vector3(0, 1, 0)], [0, 1, 5, 4, Vector3(0, -1, 0)]]
	for f in faces:
		var a: Vector3 = p[f[0]]
		var b: Vector3 = p[f[1]]
		var cc: Vector3 = p[f[2]]
		var d: Vector3 = p[f[3]]
		var n: Vector3 = f[4]
		for tri in [[a, b, cc], [a, cc, d]]:
			for v in tri:
				s.set_normal(n)
				s.set_uv(Vector2(v.x + v.z, v.y) * 0.5)
				s.add_vertex(v)


# ---------------------------------------------------------------- toits et planchers
func _build_roofs() -> void:
	for c in roof_root.get_children():
		c.queue_free()
	roof_nodes.clear()
	floor_h.clear()
	var seen := {}
	var floor_cells := {}
	for k in roofs:
		if seen.has(k):
			continue
		# composante connexe de toits du même matériau
		var mat: String = roofs[k]
		var comp := []
		var stack := [k]
		seen[k] = true
		while stack.size() > 0:
			var q: Vector2i = stack.pop_back()
			comp.append(q)
			for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
				var n: Vector2i = q + d
				if roofs.has(n) and not seen.has(n) and roofs[n] == mat:
					seen[n] = true
					stack.append(n)
		var r := Rect2i(comp[0], Vector2i.ONE)
		for q in comp:
			r = r.expand(q).expand(q + Vector2i.ONE)
		var top := -100.0
		var low := 100.0
		for q in comp:
			top = maxf(top, ground_y(q.x, q.y))
			low = minf(low, ground_y(q.x, q.y))
		var fh := top + 0.08
		for q in comp:
			if not blocks.has(q) or not _is_wallish(blocks[q][0]):
				floor_h[q] = fh
				floor_cells[q] = true
		var node := Node3D.new()
		roof_root.add_child(node)
		var full := comp.size() == r.size.x * r.size.y
		_roof_mesh(node, comp, r, mat, top + WALL_H, full)
		_floor_mesh(node, comp, fh)
		roof_nodes.append({"node": node, "rect": r, "roof": node.get_child(0) if node.get_child_count() > 0 else null})
	terrain.set_building_floor(floor_cells)
	for k in items.keys():
		# les meubles se recalent sur les planchers (seulement si la hauteur a changé)
		if absf(items[k].position.y - floor_at(k.x, k.y)) > 0.01:
			_rebuild_item(k)
	_apply_roof_visibility()


func _roof_material(mat: String) -> String:
	match mat:
		"planks", "log": return "thatch"
		"glass": return "glass"
		_: return "roof_tiles"


func _roof_mesh(node: Node3D, comp: Array, r: Rect2i, mat: String, base_y: float, full: bool) -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var gable := SurfaceTool.new()
	gable.begin(Mesh.PRIMITIVE_TRIANGLES)
	var ov := 0.45
	if full:
		var x0 := r.position.x * T - ov
		var z0 := r.position.y * T - ov
		var x1 := r.end.x * T + ov
		var z1 := r.end.y * T + ov
		var along_x := r.size.x >= r.size.y
		var half := ((z1 - z0) if along_x else (x1 - x0)) / 2.0
		var rise := clampf(half * 0.65, 0.8, 4.0)
		var y0 := base_y + 0.05
		if along_x:
			var zm := (z0 + z1) / 2
			_quad(st, Vector3(x0, y0, z0), Vector3(x1, y0, z0), Vector3(x1, y0 + rise, zm), Vector3(x0, y0 + rise, zm))
			_quad(st, Vector3(x1, y0, z1), Vector3(x0, y0, z1), Vector3(x0, y0 + rise, zm), Vector3(x1, y0 + rise, zm))
			for gx in [x0 + ov, x1 - ov]:
				_tri(gable, Vector3(gx, y0, z0 + ov), Vector3(gx, y0, z1 - ov), Vector3(gx, y0 + rise * (half - ov) / half, zm))
		else:
			var xm := (x0 + x1) / 2
			_quad(st, Vector3(x0, y0, z1), Vector3(x0, y0, z0), Vector3(xm, y0 + rise, z0), Vector3(xm, y0 + rise, z1))
			_quad(st, Vector3(x1, y0, z0), Vector3(x1, y0, z1), Vector3(xm, y0 + rise, z1), Vector3(xm, y0 + rise, z0))
			for gz in [z0 + ov, z1 - ov]:
				_tri(gable, Vector3(x0 + ov, y0, gz), Vector3(x1 - ov, y0, gz), Vector3(xm, y0 + rise * (half - ov) / half, gz))
	else:
		for q in comp:
			var x0: float = q.x * T - 0.1
			var z0: float = q.y * T - 0.1
			_quad(st, Vector3(x0, base_y + 0.3, z0), Vector3(x0 + T + 0.2, base_y + 0.3, z0),
				Vector3(x0 + T + 0.2, base_y + 0.3, z0 + T + 0.2), Vector3(x0, base_y + 0.3, z0 + T + 0.2))
	st.generate_tangents()
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = _mat(_roof_material(mat))
	node.add_child(mi)
	if full:
		var gm := MeshInstance3D.new()
		gm.mesh = gable.commit()
		gm.material_override = _mat("plaster")
		mi.add_child(gm)


func _floor_mesh(node: Node3D, comp: Array, fh: float) -> void:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for q in comp:
		var x0: float = q.x * T
		var z0: float = q.y * T
		_quad(st, Vector3(x0, fh, z0), Vector3(x0 + T, fh, z0), Vector3(x0 + T, fh, z0 + T), Vector3(x0, fh, z0 + T))
	st.generate_tangents()
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = _mat("floor")
	node.add_child(mi)


func _quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3) -> void:
	_tri(st, a, b, c)
	_tri(st, a, c, d)


func _tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3) -> void:
	var n := (b - a).cross(c - a)
	var up := n.normalized() if n.y >= 0 else -n.normalized()
	# une seule face ; les matériaux de toit sont affichés des deux côtés (cull désactivé)
	for v in [a, b, c]:
		st.set_normal(up)
		st.set_uv(Vector2(v.x + v.z * 0.3, v.y + v.z) * 0.5 if absf(n.y) < 0.9 * n.length() else Vector2(v.x, v.z) * 0.5)
		st.add_vertex(v)


func set_roof_mode(mode: String) -> void:
	roof_mode = mode
	_apply_roof_visibility()


## Cases dont le toit doit disparaître (caméra dedans, personnage suivi dedans).
func set_focus_tiles(tiles: Array) -> void:
	var d := {}
	for t in tiles:
		d[t] = true
	if d.hash() != hidden_roof_tiles.hash():
		hidden_roof_tiles = d
		_apply_roof_visibility()


## Vue en coupe (comme dans les Sims) : en vue rapprochée, les toits autour du
## point regardé disparaissent pour montrer les intérieurs.
func set_cutaway(center: Vector3, radius: float) -> void:
	if center.distance_to(cut_center) < 1.0 and absf(radius - cut_radius) < 1.0:
		return
	cut_center = center
	cut_radius = radius
	_apply_roof_visibility()


func _apply_roof_visibility() -> void:
	for rn in roof_nodes:
		var roof = rn["roof"]
		if roof == null:
			continue
		var vis := roof_mode == "on"
		if roof_mode == "auto":
			vis = true
			var r: Rect2i = rn["rect"]
			for t in hidden_roof_tiles:
				if r.has_point(t):
					vis = false
			if cut_radius > 0:
				var c := Vector3((r.position.x + r.size.x / 2.0) * T, 0, (r.position.y + r.size.y / 2.0) * T)
				if Vector2(c.x - cut_center.x, c.z - cut_center.z).length() < cut_radius:
					vis = false
		roof.visible = vis


func roof_rect_at(t: Vector2i) -> Rect2i:
	for rn in roof_nodes:
		if rn["rect"].has_point(t):
			return rn["rect"]
	return Rect2i()


# ---------------------------------------------------------------- objets et meubles
func _rebuild_item(k: Vector2i) -> void:
	if items.has(k):
		items[k].queue_free()
		items.erase(k)
	doors.erase(k)
	lights.erase(k)
	if not blocks.has(k):
		return
	var t: String = blocks[k][0]
	if t in WALLS or t == "fence":
		return
	var node := Node3D.new()
	var base := floor_at(k.x, k.y)
	node.position = Vector3(k.x * T + T / 2, base, k.y * T + T / 2)
	node.rotation.y = _facing(k, t)
	add_child(node)
	items[k] = node
	match t:
		"door", "iron_door":
			_make_door(node, k, t)
		"fence_gate":
			pass
		"bed": node.add_child(Assets.fitted("res://assets/furniture/BedDouble.fbx", 1.95))
		"table": node.add_child(Assets.fitted("res://assets/furniture/Table.fbx", 1.5))
		"chair": node.add_child(Assets.fitted("res://assets/furniture/Chair.fbx", 1.0, true))
		"stool": node.add_child(Assets.fitted("res://assets/furniture/Stool.fbx", 0.55, true))
		"sofa": node.add_child(Assets.fitted("res://assets/furniture/Sofa.fbx", 1.9))
		"bookshelf": node.add_child(Assets.fitted("res://assets/furniture/Bookcase_Books.fbx", 2.1, true))
		"wardrobe": node.add_child(Assets.fitted("res://assets/furniture/Closet.fbx", 2.1, true))
		"nightstand": node.add_child(Assets.fitted("res://assets/furniture/NightStand.fbx", 0.65, true))
		"lamp": node.add_child(Assets.fitted("res://assets/furniture/Lamp.fbx", 1.6, true))
		"plant_pot": node.add_child(Assets.fitted("res://assets/furniture/Plant.fbx", 1.1, true))
		"barrel": node.add_child(Assets.fitted("res://assets/props/Barrel.fbx", 1.0, true))
		"chest":
			var ch := Assets.fitted("res://assets/props/Chest.fbx", 1.1)
			for mi in ch.find_children("*", "MeshInstance3D", true, false):
				mi.material_override = _mat("chest")
			node.add_child(ch)
		"well": node.add_child(Assets.fitted("res://assets/props/Well.fbx", 1.9))
		"crafting_table":
			var tbl := Assets.fitted("res://assets/furniture/Table.fbx", 1.5)
			node.add_child(tbl)
			var top := Assets.bounds(tbl).end.y
			var hm := Assets.fitted("res://assets/props/Hammer_Small.fbx", 0.45, "max")
			hm.position = Vector3(0.2, top + 0.03, 0.1)
			hm.rotation = Vector3(PI / 2, 0.4, 0)
			node.add_child(hm)
			var ax := Assets.fitted("res://assets/props/Axe.fbx", 0.6, "max")
			ax.position = Vector3(-0.3, top + 0.03, -0.1)
			ax.rotation = Vector3(PI / 2, -0.6, 0)
			node.add_child(ax)
		"furnace": _make_furnace(node)
		"anvil": _make_anvil(node)
		"campfire": _make_campfire(node)
		"torch": _make_torch(node)
		"rug":
			var pm := PlaneMesh.new()
			pm.size = Vector2(1.8, 1.3)
			var mi := MeshInstance3D.new()
			mi.mesh = pm
			mi.position.y = 0.02
			mi.material_override = _mat("carpet")
			node.add_child(mi)
		"sign":
			_box_node(node, Vector3(0, 0.6, 0), Vector3(0.12, 1.2, 0.12), _mat("planks"))
			_box_node(node, Vector3(0, 1.2, 0), Vector3(0.9, 0.5, 0.08), _mat("planks"))
		"trap":
			_box_node(node, Vector3(0, 0.05, 0), Vector3(1.0, 0.1, 1.0), Assets.color_mat(Color(0.25, 0.25, 0.27), 0, 0.4))
		"scarecrow":
			_box_node(node, Vector3(0, 0.9, 0), Vector3(0.12, 1.8, 0.12), _mat("planks"))
			_box_node(node, Vector3(0, 1.4, 0), Vector3(1.2, 0.1, 0.1), _mat("planks"))
			var head := MeshInstance3D.new()
			var sm := SphereMesh.new()
			sm.radius = 0.2
			sm.height = 0.4
			head.mesh = sm
			head.position.y = 1.9
			head.material_override = Assets.color_mat(Color(0.85, 0.75, 0.45))
			node.add_child(head)
		_:
			_box_node(node, Vector3(0, 0.5, 0), Vector3(1, 1, 1), Assets.color_mat(Color(0.6, 0.5, 0.4)))
	if LIGHT_BLOCKS.has(t):
		var spec: Array = LIGHT_BLOCKS[t]
		lights[k] = [node.position + Vector3(0, 1.4 if t != "campfire" else 0.8, 0), spec[0], spec[1], t]


func _facing(k: Vector2i, t: String) -> float:
	# les chaises regardent la table voisine ; le reste tourne le dos au mur le plus proche
	var dirs := [Vector2i(0, 1), Vector2i(1, 0), Vector2i(0, -1), Vector2i(-1, 0)]
	if t in ["chair", "stool"]:
		for d in dirs:
			var nb = blocks.get(k + d)
			if nb != null and nb[0] == "table":
				return atan2(float(d.x), float(d.y))
	if t in DOORS:
		return 0.0
	for d in dirs:
		var nb = blocks.get(k + d)
		if nb != null and _is_wallish(nb[0]):
			return atan2(float(-d.x), float(-d.y))
	return Assets.hash2(k.x, k.y, 5) * 4.0


func _box_node(parent: Node3D, pos: Vector3, size: Vector3, mat: Material) -> MeshInstance3D:
	var bm := BoxMesh.new()
	bm.size = size
	var mi := MeshInstance3D.new()
	mi.mesh = bm
	mi.position = pos
	mi.material_override = mat
	parent.add_child(mi)
	return mi


func _make_door(node: Node3D, k: Vector2i, t: String) -> void:
	var axis_x := true
	for d in [Vector2i(0, 1), Vector2i(0, -1)]:
		var nb = blocks.get(k + d)
		if nb != null and _is_wallish(nb[0]):
			axis_x = false
	node.rotation.y = 0.0 if axis_x else PI / 2
	var pivot := Node3D.new()
	pivot.position = Vector3(-T / 2 + 0.3, 0, 0)
	node.add_child(pivot)
	var panel := Assets.fitted("res://assets/furniture/Door1.fbx", WALL_H - 0.6, true)
	var b := Assets.bounds(panel)
	panel.position = Vector3(b.size.x / 2 if b.size.x > b.size.z else 0.0, 0, 0)
	pivot.add_child(panel)
	if t == "iron_door":
		for mi in panel.find_children("*", "MeshInstance3D", true, false):
			mi.material_override = Assets.color_mat(Color(0.6, 0.62, 0.66), 0, 0.3)
	doors[k] = pivot


## Ouvre les portes quand quelqu'un passe.
func animate_doors(people_tiles: Dictionary, delta: float) -> void:
	for k in doors:
		var open := false
		for d in [Vector2i(0, 0), Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			if people_tiles.has(k + d):
				open = true
		var pivot: Node3D = doors[k]
		pivot.rotation.y = lerpf(pivot.rotation.y, -1.4 if open else 0.0, minf(1.0, delta * 4.0))


func _make_furnace(node: Node3D) -> void:
	_box_node(node, Vector3(0, 0.8, 0), Vector3(1.4, 1.6, 1.3), _mat("cobblestone"))
	_box_node(node, Vector3(0, 1.75, 0), Vector3(0.5, 0.5, 0.5), _mat("cobblestone"))
	var glow := _box_node(node, Vector3(0, 0.55, 0.62), Vector3(0.7, 0.45, 0.08), Assets.color_mat(Color(1.0, 0.45, 0.1), 4.0))
	glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.add_child(Effects.smoke(Vector3(0, 2.1, 0), 0.6))


func _make_anvil(node: Node3D) -> void:
	var iron := Assets.color_mat(Color(0.2, 0.2, 0.23), 0, 0.35)
	iron.metallic = 0.8
	_box_node(node, Vector3(0, 0.25, 0), Vector3(0.6, 0.5, 0.5), _mat("log"))
	_box_node(node, Vector3(0, 0.62, 0), Vector3(0.9, 0.25, 0.35), iron)
	_box_node(node, Vector3(0.5, 0.66, 0), Vector3(0.3, 0.15, 0.2), iron)


func _make_campfire(node: Node3D) -> void:
	var stone := Assets.mesh("res://assets/nature/Pebble_Round_1.gltf", 0.32, false)
	for i in 9:
		var mi := MeshInstance3D.new()
		mi.mesh = stone
		var a := i * TAU / 9
		mi.position = Vector3(cos(a) * 0.65, 0, sin(a) * 0.65)
		node.add_child(mi)
	for i in 4:
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.07
		cyl.bottom_radius = 0.08
		cyl.height = 0.9
		var mi := MeshInstance3D.new()
		mi.mesh = cyl
		mi.material_override = _mat("log")
		mi.position = Vector3(0, 0.25, 0)
		mi.rotation = Vector3(0.9, i * PI / 2, 0)
		node.add_child(mi)
	node.add_child(Effects.fire(Vector3(0, 0.15, 0), 1.0))
	node.add_child(Effects.smoke(Vector3(0, 1.2, 0), 0.8))


func _make_torch(node: Node3D) -> void:
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.05
	cyl.bottom_radius = 0.06
	cyl.height = 1.5
	var mi := MeshInstance3D.new()
	mi.mesh = cyl
	mi.position.y = 0.75
	mi.material_override = _mat("log")
	node.add_child(mi)
	node.add_child(Effects.fire(Vector3(0, 1.55, 0), 0.3))
