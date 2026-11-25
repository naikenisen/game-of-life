class_name Assets
extends RefCounted
## Chargement et préparation des assets (cache, mise à l'échelle, matériaux).

const T := 2.0  # taille d'une case de la simulation, en mètres

const MALE := ["Adventurer", "Beach", "Casual_2", "Casual_Hoodie", "Farmer", "King", "Punk", "Suit", "Worker"]
const FEMALE := ["Adventurer", "Casual", "Formal", "Medieval", "Punk", "Suit", "Witch", "Worker"]

static var _scenes := {}
static var _meshes := {}
static var _mats := {}
static var anim_lib: AnimationLibrary


static func scene(path: String) -> PackedScene:
	if not _scenes.has(path):
		_scenes[path] = load(path)
	return _scenes[path]


static func character_path(gender: String, outfit: int) -> String:
	var list: Array = FEMALE if gender == "f" else MALE
	var folder := "female" if gender == "f" else "male"
	return "res://assets/characters/%s/%s.glb" % [folder, list[outfit % list.size()]]


static func animations() -> AnimationLibrary:
	if anim_lib == null:
		anim_lib = load("res://generated/ual_library.res")
	return anim_lib


## Boîte englobante (espace du nœud racine) de tous les MeshInstance3D d'une scène.
static func bounds(root: Node3D) -> AABB:
	var out := AABB()
	var first := true
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var xf := _relative_xform(root, mi)
		var box: AABB = xf * mi.get_aabb()
		if first:
			out = box
			first = false
		else:
			out = out.merge(box)
	return out


static func _relative_xform(root: Node3D, n: Node3D) -> Transform3D:
	var xf := Transform3D()
	var cur: Node = n
	while cur != null and cur != root:
		if cur is Node3D:
			xf = (cur as Node3D).transform * xf
		cur = cur.get_parent()
	return xf


## Instancie un modèle et le met à l'échelle pour que sa plus grande dimension
## horizontale (ou sa hauteur si by_height = true, ou sa plus grande dimension si
## by_height = "max") vaille `size`. Le modèle est posé au sol, centré.
static func fitted(path: String, size: float, by_height: Variant = false) -> Node3D:
	var inst: Node3D = scene(path).instantiate()
	var holder := Node3D.new()
	holder.add_child(inst)
	var b := bounds(inst)
	var ref := maxf(b.size.x, b.size.z)
	if typeof(by_height) == TYPE_STRING:
		ref = maxf(ref, b.size.y)
	elif by_height:
		ref = b.size.y
	var s := size / maxf(ref, 0.0001)
	inst.scale = Vector3.ONE * s
	inst.position = Vector3(-(b.position.x + b.size.x / 2) * s, -b.position.y * s, -(b.position.z + b.size.z / 2) * s)
	return holder


## Maillage unique (fusion des surfaces) d'un modèle statique, normalisé, pour MultiMesh.
static func mesh(path: String, size: float, by_height := true) -> Mesh:
	var key := "%s|%s|%s" % [path, size, by_height]
	if _meshes.has(key):
		return _meshes[key]
	var inst: Node3D = scene(path).instantiate()
	var b := bounds(inst)
	var ref := b.size.y if by_height else maxf(b.size.x, b.size.z)
	var s := size / maxf(ref, 0.0001)
	var base := Transform3D(Basis().scaled(Vector3.ONE * s),
		Vector3(-(b.position.x + b.size.x / 2) * s, -b.position.y * s, -(b.position.z + b.size.z / 2) * s))
	var im := ImporterMesh.new()
	for mi in inst.find_children("*", "MeshInstance3D", true, false):
		var xf := base * _relative_xform(inst, mi)
		for si in mi.mesh.get_surface_count():
			var st := SurfaceTool.new()
			st.create_from(mi.mesh, si)
			var arrays := st.commit_to_arrays()
			var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var norms = arrays[Mesh.ARRAY_NORMAL]
			for i in verts.size():
				verts[i] = xf * verts[i]
			arrays[Mesh.ARRAY_VERTEX] = verts
			if norms != null:
				var nb := xf.basis.inverse().transposed()
				for i in norms.size():
					norms[i] = (nb * norms[i]).normalized()
				arrays[Mesh.ARRAY_NORMAL] = norms
			arrays[Mesh.ARRAY_BONES] = null
			arrays[Mesh.ARRAY_WEIGHTS] = null
			var mat: Material = mi.get_active_material(si)
			im.add_surface(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, mat)
	inst.free()
	# niveaux de détail automatiques : les arbres lointains coûtent beaucoup moins cher
	im.generate_lods(25.0, 60.0, [])
	var am := im.get_mesh()
	_meshes[key] = am
	return am


## Matériau PBR à partir des textures Poly Haven (albedo / normal / ARM).
static func pbr(name: String, uv_scale := 0.5, triplanar := true) -> StandardMaterial3D:
	var key := "%s|%s|%s" % [name, uv_scale, triplanar]
	if _mats.has(key):
		return _mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_texture = load("res://assets/textures/%s_albedo.jpg" % name)
	m.normal_enabled = true
	m.normal_texture = load("res://assets/textures/%s_normal.jpg" % name)
	m.ao_enabled = true
	m.ao_texture = load("res://assets/textures/%s_arm.jpg" % name)
	m.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	m.roughness_texture = m.ao_texture
	m.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	if triplanar:
		m.uv1_triplanar = true
		m.uv1_world_triplanar = true
		m.uv1_scale = Vector3.ONE * uv_scale
	_mats[key] = m
	return m


static func color_mat(c: Color, emission := 0.0, rough := 0.8) -> StandardMaterial3D:
	var key := "c|%s|%s|%s" % [c, emission, rough]
	if _mats.has(key):
		return _mats[key]
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	if emission > 0:
		m.emission_enabled = true
		m.emission = c
		m.emission_energy_multiplier = emission
	_mats[key] = m
	return m


static func tile_to_world(x: float, y: float) -> Vector3:
	return Vector3(x * T + T * 0.5, 0.0, y * T + T * 0.5)


static func hash2(x: int, y: int, salt := 0) -> float:
	var h := (x * 374761393 + y * 668265263 + salt * 2147483647) & 0x7fffffff
	h = (h ^ (h >> 13)) * 1274126177 & 0x7fffffff
	return float(h % 10000) / 10000.0
