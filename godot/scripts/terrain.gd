class_name Terrain
extends Node3D
## Sol, relief, eau, végétation, rochers, minerais, cultures et objets au sol.
## Tout est découpé en blocs de CH x CH cases reconstruits quand ils changent.

const T := Assets.T
const CH := 24
const SUB := 2  # sommets par case et par axe

enum G { WATER, SAND, GRASS, DIRT, FARMLAND, STONE_FLOOR, GRAVEL }
enum F { NONE, TREE, BUSH, TALL_GRASS, ROCK, COAL, IRON, GOLD, DIAMOND, CLAY, MUSHROOM, GRAVEL, SAPLING }

var w := 0
var h := 0
var ground := PackedInt32Array()
var feature := PackedInt32Array()
var amount := PackedInt32Array()
var crops := {}         # Vector2i -> stade
var ground_items := {}  # Vector2i -> true
var noise := FastNoiseLite.new()
var base_h := PackedFloat32Array()   # hauteur de base par case
var vert_h := PackedFloat32Array()   # hauteur par sommet ((w*SUB+1) x (h*SUB+1))
var chunks := {}                     # Vector2i -> Node3D
var dirty_chunks := {}
var terrain_mat: ShaderMaterial
var veg := {}                        # clé -> Mesh
var building_floor := {}             # Vector2i -> true : cases intérieures (pas d'herbe)


func setup(d: Dictionary) -> void:
	w = d["w"]
	h = d["h"]
	ground = PackedInt32Array(d["ground"])
	feature = PackedInt32Array(d["feature"])
	amount = PackedInt32Array(d["amount"])
	for c in d["crops"]:
		crops[Vector2i(c[0], c[1])] = c[2]
	noise.seed = 1234
	noise.frequency = 0.045
	noise.fractal_octaves = 3
	_make_material()
	_load_vegetation()
	_compute_heights()
	for cy in ceili(float(h) / CH):
		for cx in ceili(float(w) / CH):
			_build_chunk(Vector2i(cx, cy))
	_make_water()


func _make_material() -> void:
	terrain_mat = ShaderMaterial.new()
	terrain_mat.shader = load("res://shaders/terrain.gdshader")
	for pair in [["grass", "grass"], ["forest", "forest"], ["sand", "sand"], ["soil", "soil"], ["rock", "rock"], ["gravel", "gravel"]]:
		terrain_mat.set_shader_parameter(pair[0] + "_a", load("res://assets/textures/%s_albedo.jpg" % pair[1]))
		terrain_mat.set_shader_parameter(pair[0] + "_n", load("res://assets/textures/%s_normal.jpg" % pair[1]))
	var nt := NoiseTexture2D.new()
	nt.seamless = true
	nt.width = 256
	nt.height = 256
	var n := FastNoiseLite.new()
	n.frequency = 0.02
	nt.noise = n
	terrain_mat.set_shader_parameter("macro_noise", nt)


func _load_vegetation() -> void:
	var N := "res://assets/nature/%s.gltf"
	for i in range(1, 6):
		veg["tree_common_%d" % i] = Assets.mesh(N % ("CommonTree_%d" % i), 7.5)
	for i in range(1, 4):
		veg["tree_pine_%d" % i] = Assets.mesh(N % ("Pine_%d" % i), 9.0)
		veg["tree_birch_%d" % i] = Assets.mesh(N % ("Birch_%d" % i), 8.0)
	veg["sapling"] = Assets.mesh(N % "CommonTree_2", 1.2)
	veg["bush"] = Assets.mesh(N % "Bush_Common", 1.3)
	veg["bush_berries"] = Assets.mesh(N % "Bush_Common_Flowers", 1.4)
	veg["bush_large"] = Assets.mesh(N % "Bush_Large", 1.8)
	veg["tall_grass"] = Assets.mesh(N % "Grass_Wispy_Tall", 0.9)
	veg["fern"] = Assets.mesh(N % "Fern_1", 0.8)
	veg["grass_short"] = Assets.mesh(N % "Grass_Common_Short", 0.35)
	veg["grass_tall"] = Assets.mesh(N % "Grass_Common_Tall", 0.6)
	veg["clover"] = Assets.mesh(N % "Clover_1", 0.25)
	veg["flowers_a"] = Assets.mesh(N % "Flower_3_Group", 0.45)
	veg["flowers_b"] = Assets.mesh(N % "Flower_4_Group", 0.45)
	veg["plant"] = Assets.mesh(N % "Plant_1", 0.6)
	veg["mushroom"] = Assets.mesh(N % "Mushroom_RedCap", 0.35)
	veg["mushroom2"] = Assets.mesh(N % "Mushroom_Common", 0.3)
	veg["rock_big_1"] = Assets.mesh(N % "Rock_Big_1", 2.4)
	veg["rock_big_2"] = Assets.mesh(N % "Rock_Big_2", 2.2)
	veg["rock_med_1"] = Assets.mesh(N % "Rock_Medium_1", 1.0)
	veg["rock_med_2"] = Assets.mesh(N % "Rock_Medium_2", 0.9)
	veg["rock_med_3"] = Assets.mesh(N % "Rock_Medium_3", 0.8)
	veg["pebble_1"] = Assets.mesh(N % "Pebble_Round_1", 0.35, false)
	veg["pebble_2"] = Assets.mesh(N % "Pebble_Square_3", 0.4, false)
	veg["wheat"] = Assets.mesh(N % "Grass_Wheat", 1.1)
	for ore in [["coal", Color(0.08, 0.08, 0.09), 0.0], ["iron", Color(0.85, 0.55, 0.35), 0.0],
			["gold", Color(1.0, 0.8, 0.2), 0.4], ["diamond", Color(0.4, 0.95, 1.0), 1.2]]:
		var pm := PrismMesh.new()
		pm.size = Vector3(0.35, 0.55, 0.35)
		pm.material = Assets.color_mat(ore[1], ore[2], 0.35)
		veg["ore_" + ore[0]] = pm
	var crate := BoxMesh.new()
	crate.size = Vector3(0.45, 0.3, 0.35)
	crate.material = Assets.pbr("planks", 2.0)
	veg["item_pile"] = crate


# ---------------------------------------------------------------- hauteurs
func idx(x: int, y: int) -> int:
	return y * w + x


func _is_mountain(x: int, y: int) -> bool:
	var f := feature[idx(x, y)]
	if not (f >= F.ROCK and f <= F.DIAMOND):
		return false
	var n := 0
	for dy in [-1, 0, 1]:
		for dx in [-1, 0, 1]:
			var xx: int = x + dx
			var yy: int = y + dy
			if xx >= 0 and yy >= 0 and xx < w and yy < h:
				var ff := feature[idx(xx, yy)]
				if ff >= F.ROCK and ff <= F.DIAMOND:
					n += 1
	return n >= 4


func _tile_height(x: int, y: int) -> float:
	var g := ground[idx(x, y)]
	var n := noise.get_noise_2d(x, y)
	if _is_mountain(x, y):
		# plus on s'enfonce dans le massif, plus c'est haut
		var depth := 0
		for r in range(1, 5):
			var all_rock := true
			for d in [Vector2i(r, 0), Vector2i(-r, 0), Vector2i(0, r), Vector2i(0, -r)]:
				var xx := clampi(x + d.x, 0, w - 1)
				var yy := clampi(y + d.y, 0, h - 1)
				var ff := feature[idx(xx, yy)]
				if not (ff >= F.ROCK and ff <= F.DIAMOND):
					all_rock = false
			if not all_rock:
				break
			depth = r
		return 3.0 + depth * 2.2 + n * 1.5 + noise.get_noise_2d(x * 3.1, y * 3.1) * 1.0
	match g:
		G.WATER:
			var deep := 0
			for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
				var xx := clampi(x + d.x, 0, w - 1)
				var yy := clampi(y + d.y, 0, h - 1)
				if ground[idx(xx, yy)] == G.WATER:
					deep += 1
			return -0.6 - deep * 0.35
		G.SAND:
			return 0.08 + n * 0.12
		G.STONE_FLOOR, G.GRAVEL:
			return 0.45 + n * 0.3
		G.FARMLAND:
			return 0.22 + n * 0.3
		_:
			return 0.3 + n * 0.45


func _compute_heights() -> void:
	base_h.resize(w * h)
	for y in h:
		for x in w:
			base_h[idx(x, y)] = _tile_height(x, y)
	var vw := w * SUB + 1
	var vh := h * SUB + 1
	vert_h.resize(vw * vh)
	for vy in vh:
		for vx in vw:
			vert_h[vy * vw + vx] = _vertex_height(vx, vy)


func _vertex_height(vx: int, vy: int) -> float:
	# un sommet au milieu d'une case prend sa hauteur ; sur un bord/coin, la moyenne des cases voisines
	var tiles := _tiles_of_vertex(vx, vy)
	var s := 0.0
	for t in tiles:
		s += base_h[idx(t.x, t.y)]
	return s / tiles.size()


func _tiles_of_vertex(vx: int, vy: int) -> Array:
	var xs := []
	var ys := []
	if vx % SUB == 0:
		xs = [vx / SUB - 1, vx / SUB]
	else:
		xs = [vx / SUB]
	if vy % SUB == 0:
		ys = [vy / SUB - 1, vy / SUB]
	else:
		ys = [vy / SUB]
	var out := []
	for yy in ys:
		for xx in xs:
			if xx >= 0 and yy >= 0 and xx < w and yy < h:
				out.append(Vector2i(xx, yy))
	return out


## Hauteur du sol à une position monde (interpolation bilinéaire).
func height_at(px: float, pz: float) -> float:
	var fx := clampf(px / T * SUB, 0, w * SUB - 0.001)
	var fz := clampf(pz / T * SUB, 0, h * SUB - 0.001)
	var x0 := int(fx)
	var z0 := int(fz)
	var tx := fx - x0
	var tz := fz - z0
	var vw := w * SUB + 1
	var a := vert_h[z0 * vw + x0]
	var b := vert_h[z0 * vw + x0 + 1]
	var c := vert_h[(z0 + 1) * vw + x0]
	var d := vert_h[(z0 + 1) * vw + x0 + 1]
	return lerpf(lerpf(a, b, tx), lerpf(c, d, tx), tz)


func tile_height(x: int, y: int) -> float:
	return height_at(x * T + T * 0.5, y * T + T * 0.5)


func is_water(x: int, y: int) -> bool:
	return x >= 0 and y >= 0 and x < w and y < h and ground[idx(x, y)] == G.WATER


# ---------------------------------------------------------------- mises à jour
func update_cell(c: Array) -> void:
	var x: int = c[0]
	var y: int = c[1]
	var i := idx(x, y)
	var changed_shape: bool = ground[i] != c[2] or ((feature[i] >= F.ROCK and feature[i] <= F.DIAMOND) != (c[3] >= F.ROCK and c[3] <= F.DIAMOND))
	# rien de visible n'a changé (ex : un arbre entamé mais encore debout) -> pas de reconstruction
	var key0 := Vector2i(x, y)
	var visible_change: bool = changed_shape or feature[i] != c[3] or (amount[i] > 0) != (c[4] > 0) \
		or crops.get(key0, -1) != c[8]
	ground[i] = c[2]
	feature[i] = c[3]
	amount[i] = c[4]
	var key := Vector2i(x, y)
	if c[8] >= 0:
		crops[key] = c[8]
	else:
		crops.erase(key)
	if changed_shape:
		# le relief change (roche minée) : recalcul local des hauteurs
		for yy in range(maxi(0, y - 2), mini(h, y + 3)):
			for xx in range(maxi(0, x - 2), mini(w, x + 3)):
				base_h[idx(xx, yy)] = _tile_height(xx, yy)
		var vw := w * SUB + 1
		for vy in range(maxi(0, (y - 2) * SUB), mini(h * SUB + 1, (y + 3) * SUB + 1)):
			for vx in range(maxi(0, (x - 2) * SUB), mini(w * SUB + 1, (x + 3) * SUB + 1)):
				vert_h[vy * vw + vx] = _vertex_height(vx, vy)
		for dy in [-1, 0, 1]:
			for dx in [-1, 0, 1]:
				_mark(x + dx * 3, y + dy * 3)
	if visible_change:
		_mark(x, y)


func set_ground_items(items: Dictionary) -> void:
	for k in ground_items:
		_mark(k.x, k.y)
	ground_items = items
	for k in ground_items:
		_mark(k.x, k.y)


func set_building_floor(cells: Dictionary) -> void:
	for k in building_floor:
		_mark(k.x, k.y)
	building_floor = cells
	for k in building_floor:
		_mark(k.x, k.y)


func _mark(x: int, y: int) -> void:
	if x < 0 or y < 0 or x >= w or y >= h:
		return
	dirty_chunks[Vector2i(x / CH, y / CH)] = true


func flush(max_chunks := 3) -> void:
	var n := 0
	for k in dirty_chunks.keys():
		_build_chunk(k)
		dirty_chunks.erase(k)
		n += 1
		if n >= max_chunks:
			break


# ---------------------------------------------------------------- construction d'un bloc
func _weights(x: int, y: int) -> Array:
	# [herbe, sous-bois, sable, terre, roche, gravier]
	var i := idx(x, y)
	var g := ground[i]
	var f := feature[i]
	if _is_mountain(x, y) or g == G.STONE_FLOOR:
		return [0, 0, 0, 0, 1, 0]
	match g:
		G.WATER:
			return [0, 0, 1, 0, 0, 0]
		G.SAND:
			return [0, 0, 1, 0, 0, 0.3 if f == F.GRAVEL or f == F.CLAY else 0.0]
		G.GRAVEL:
			return [0, 0, 0, 0, 0.3, 1]
		G.FARMLAND:
			return [0, 0, 0, 1, 0, 0]
		G.DIRT:
			return [0.2, 0.5, 0, 0.6, 0, 0]
	if f == F.TREE or f == F.MUSHROOM or f == F.SAPLING:
		return [0.35, 1, 0, 0, 0, 0]
	return [1, 0.08, 0, 0, 0, 0]


func _build_chunk(k: Vector2i) -> void:
	if chunks.has(k):
		chunks[k].queue_free()
	var node := Node3D.new()
	node.set_meta("chunk", k)
	add_child(node)
	chunks[k] = node
	var x0 := k.x * CH
	var y0 := k.y * CH
	var x1 := mini(w, x0 + CH)
	var y1 := mini(h, y0 + CH)
	node.add_child(_ground_mesh(x0, y0, x1, y1))
	_scatter(node, x0, y0, x1, y1)


func _ground_mesh(x0: int, y0: int, x1: int, y1: int) -> MeshInstance3D:
	var vw := w * SUB + 1
	var nx := (x1 - x0) * SUB + 1
	var nz := (y1 - y0) * SUB + 1
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var cols := PackedColorArray()
	var cust := PackedFloat32Array()
	var uvs := PackedVector2Array()
	var step := T / SUB
	for j in nz:
		for i in nx:
			var vx := x0 * SUB + i
			var vy := y0 * SUB + j
			var hh := vert_h[vy * vw + vx]
			verts.append(Vector3(vx * step, hh, vy * step))
			uvs.append(Vector2(vx, vy) * 0.25)
			var hl := vert_h[vy * vw + maxi(vx - 1, 0)]
			var hr := vert_h[vy * vw + mini(vx + 1, vw - 1)]
			var hu := vert_h[maxi(vy - 1, 0) * vw + vx]
			var hd := vert_h[mini(vy + 1, h * SUB) * vw + vx]
			norms.append(Vector3(hl - hr, 2.0 * step, hu - hd).normalized())
			var wsum := [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
			var tiles := _tiles_of_vertex(vx, vy)
			for t in tiles:
				var ww := _weights(t.x, t.y)
				for q in 6:
					wsum[q] += ww[q]
			cols.append(Color(wsum[0], wsum[1], wsum[2], wsum[3]))
			cust.append_array([wsum[4], wsum[5], 0.0, 0.0])
	var idxs := PackedInt32Array()
	for j in nz - 1:
		for i in nx - 1:
			var a := j * nx + i
			idxs.append_array([a, a + 1, a + nx, a + 1, a + nx + 1, a + nx])
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = norms
	arrays[Mesh.ARRAY_COLOR] = cols
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_CUSTOM0] = cust
	arrays[Mesh.ARRAY_INDEX] = idxs
	var am := ArrayMesh.new()
	var fmt := Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, fmt)
	am.surface_set_material(0, terrain_mat)
	var mi := MeshInstance3D.new()
	mi.mesh = am
	return mi


func _scatter(node: Node3D, x0: int, y0: int, x1: int, y1: int) -> void:
	var inst := {}   # clé de maillage -> Array[Transform3D]
	for y in range(y0, y1):
		for x in range(x0, x1):
			var i := idx(x, y)
			var f := feature[i]
			var g := ground[i]
			var c := Vector3(x * T + T * 0.5, 0, y * T + T * 0.5)
			var r1 := Assets.hash2(x, y, 1)
			var r2 := Assets.hash2(x, y, 2)
			var r3 := Assets.hash2(x, y, 3)
			var jit := Vector3((r1 - 0.5) * 0.7, 0, (r2 - 0.5) * 0.7)
			var key := Vector2i(x, y)
			if building_floor.has(key):
				continue
			match f:
				F.TREE:
					var kind := "tree_common_%d" % (1 + int(r3 * 5))
					var n := noise.get_noise_2d(x * 0.5, y * 0.5)
					if n > 0.15:
						kind = "tree_pine_%d" % (1 + int(r3 * 3))
					elif n < -0.4 and r1 > 0.5:
						kind = "tree_birch_%d" % (1 + int(r3 * 3))
					_add(inst, kind, c + jit, r1 * TAU, 0.75 + r2 * 0.4)
					_add(inst, "fern", c + Vector3(0.6, 0, -0.4), r2 * TAU, 0.8)
				F.SAPLING:
					_add(inst, "sapling", c, r1 * TAU, 1.0)
				F.BUSH:
					_add(inst, "bush_berries" if amount[i] > 0 else "bush", c + jit * 0.5, r1 * TAU, 0.9 + r2 * 0.3)
				F.TALL_GRASS:
					_add(inst, "tall_grass", c + jit, r1 * TAU, 1.0 + r3 * 0.4)
					_add(inst, "tall_grass", c - jit * 1.2, r2 * TAU, 0.8)
					if r3 > 0.6:
						_add(inst, "flowers_a" if r3 > 0.8 else "flowers_b", c + Vector3(-0.5, 0, 0.5), r1 * TAU, 1.0)
				F.MUSHROOM:
					_add(inst, "mushroom", c + jit, r1 * TAU, 1.0)
					_add(inst, "mushroom2", c + jit + Vector3(0.3, 0, 0.2), r2 * TAU, 1.0)
				F.CLAY:
					_add(inst, "pebble_1", c + jit, r1 * TAU, 1.6)
				F.GRAVEL:
					_add(inst, "pebble_2", c + jit, r1 * TAU, 1.3)
					_add(inst, "pebble_1", c - jit, r2 * TAU, 1.0)
				F.ROCK, F.COAL, F.IRON, F.GOLD, F.DIAMOND:
					if _is_mountain(x, y):
						if r1 > 0.85:
							_add(inst, "rock_big_%d" % (1 + int(r2 * 2)), c + jit - Vector3(0, 0.6, 0), r3 * TAU, 0.6 + r2 * 0.4)
					else:
						_add(inst, "rock_big_%d" % (1 + int(r2 * 2)), c + jit * 0.3, r3 * TAU, 0.7 + r1 * 0.3)
					if f >= F.COAL:
						var ore: String = ["", "", "", "", "", "ore_coal", "ore_iron", "ore_gold", "ore_diamond"][f]
						for q in 3:
							var off := Vector3(Assets.hash2(x, y, 10 + q) - 0.5, 0, Assets.hash2(x, y, 20 + q) - 0.5) * 1.3
							_add(inst, ore, c + off + Vector3(0, 0.1, 0), Assets.hash2(x, y, 30 + q) * TAU, 0.8 + q * 0.2, true)
			# herbe décorative et fleurs sur les prairies libres
			if f == F.NONE and (g == G.GRASS or g == G.DIRT):
				var d := Assets.hash2(x, y, 7)
				if d < 0.55:
					_add(inst, "grass_short", c + Vector3((r1 - 0.5) * 1.6, 0, (r3 - 0.5) * 1.6), r2 * TAU, 1.0 + r1)
				if d < 0.25:
					_add(inst, "grass_tall", c + Vector3((r3 - 0.5) * 1.5, 0, (r1 - 0.5) * 1.5), r1 * TAU, 0.9 + r2 * 0.5)
				if d > 0.93:
					_add(inst, "flowers_a" if r2 > 0.5 else "flowers_b", c + jit, r3 * TAU, 0.9)
				elif d > 0.88:
					_add(inst, "clover", c + jit, r3 * TAU, 1.3)
			if crops.has(key):
				var st: int = crops[key]
				for q in 4:
					var off := Vector3((q % 2) * 0.9 - 0.45, 0, (q / 2) * 0.9 - 0.45)
					_add(inst, "wheat", c + off, Assets.hash2(x, y, 40 + q) * TAU, 0.3 + st * 0.25)
			if ground_items.has(key):
				_add(inst, "item_pile", c + jit * 0.3, r1 * TAU, 1.0)
	for kname in inst:
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = veg[kname]
		var list: Array = inst[kname]
		mm.instance_count = list.size()
		for q in list.size():
			mm.set_instance_transform(q, list[q])
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		if kname.begins_with("tree"):
			mmi.add_to_group("tree_mm")
		if kname.begins_with("grass") or kname == "clover" or kname.begins_with("flowers") or kname.begins_with("pebble") \
				or kname in ["fern", "mushroom", "mushroom2", "tall_grass", "plant", "wheat"]:
			mmi.visibility_range_end = 65.0
			mmi.visibility_range_end_margin = 10.0
			mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
			mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		elif kname.begins_with("ore") or kname.begins_with("bush") or kname.begins_with("rock_med"):
			mmi.visibility_range_end = 160.0
		node.add_child(mmi)


func _add(inst: Dictionary, kname: String, p: Vector3, rot: float, s: float, keep_y := false) -> void:
	var y := height_at(p.x, p.z) + (p.y if keep_y or p.y < 0 else 0.0)
	if not inst.has(kname):
		inst[kname] = []
	var b := Basis(Vector3.UP, rot).scaled(Vector3.ONE * s)
	inst[kname].append(Transform3D(b, Vector3(p.x, y - 0.03, p.z)))


## Seuls les arbres proches de la caméra projettent une ombre (les ombres de
## feuillage sont la dépense principale sur les cartes graphiques modestes).
func update_tree_shadows(cam_pos: Vector3, radius: float) -> void:
	for mmi in get_tree().get_nodes_in_group("tree_mm"):
		var chunk: Node3D = mmi.get_parent()
		var k: Vector2i = chunk.get_meta("chunk", Vector2i.ZERO)
		var c := Vector3((k.x + 0.5) * CH * T, 0, (k.y + 0.5) * CH * T)
		var near := Vector2(c.x - cam_pos.x, c.z - cam_pos.z).length() < radius + CH * T * 0.7
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if near else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF


func _make_water() -> void:
	var pm := PlaneMesh.new()
	pm.size = Vector2(w * T + 400, h * T + 400)
	pm.subdivide_width = 60
	pm.subdivide_depth = 45
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/water.gdshader")
	for n in ["wave_a", "wave_b"]:
		var nt := NoiseTexture2D.new()
		nt.seamless = true
		nt.as_normal_map = true
		nt.bump_strength = 4.0
		var fn := FastNoiseLite.new()
		fn.frequency = 0.03 if n == "wave_a" else 0.05
		fn.seed = 7 if n == "wave_a" else 99
		nt.noise = fn
		mat.set_shader_parameter(n, nt)
	pm.material = mat
	var mi := MeshInstance3D.new()
	mi.mesh = pm
	mi.position = Vector3(w * T / 2, -0.32, h * T / 2)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
