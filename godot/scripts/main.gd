extends Node3D
## Scène principale : environnement (ciel, soleil, lune, brouillard), connexion à la
## simulation, création des habitants/animaux, caméras, lumières, interface.

const T := Assets.T
const MAX_LIGHTS := 28

var net: Net
var terrain: Terrain
var buildings: Buildings
var cam_rig: CameraRig
var hud: Hud
var env: Environment
var sun: DirectionalLight3D
var moon: DirectionalLight3D
var sky_mat: ProceduralSkyMaterial
var persons := {}      # id -> Person
var animals := {}      # id -> Animal3D
var people_info := {}  # id -> infos statiques
var selected: Person
var last_tick := {}
var tick_dt := 0.5
var last_tick_time := 0.0
var day_length := 1200
var night_fraction := 0.35
var world_ready := false
var light_pool := []
var minimap_timer := 0.0
var minimap_base: Image
var paused := false
var capture := {}      # options de capture d'écran automatique (tests)
var capture_t := 0.0
var flicker_t := 0.0
var sites := []
var prof := {}
var shadow_quality := "medium"
var daylight_timer := 0.0
var shadow_lights := 2


func _ready() -> void:
	_parse_args()
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
	_make_environment()
	terrain = Terrain.new()
	terrain.name = "Terrain"
	add_child(terrain)
	buildings = Buildings.new()
	buildings.name = "Buildings"
	add_child(buildings)
	cam_rig = CameraRig.new()
	cam_rig.world = self
	add_child(cam_rig)
	hud = Hud.new()
	hud.main = self
	add_child(hud)
	for i in MAX_LIGHTS:
		var l := OmniLight3D.new()
		l.visible = false
		l.shadow_enabled = false  # une ombre omni = 6 rendus de la scène : réservé à la nuit, voir _update_lights
		l.omni_attenuation = 1.4
		add_child(l)
		light_pool.append(l)
	net = Net.new()
	add_child(net)
	net.got_init.connect(_on_init)
	net.got_tick.connect(_on_tick)
	net.status_changed.connect(func(t): hud.set_status("" if t == "connecté" else "⚠ " + t))


func _parse_args() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--capture="):
			capture["path"] = a.substr(10)
		elif a.begins_with("--capture-after="):
			capture["after"] = float(a.substr(16))
		elif a.begins_with("--cam="):
			capture["cam"] = a.substr(6).split(",")
		elif a.begins_with("--select="):
			capture["select"] = int(a.substr(9))
		elif a.begins_with("--mode="):
			capture["mode"] = a.substr(7)
		elif a == "--noworld":
			capture["noworld"] = true
		elif a == "--no-animals":
			capture["no_animals"] = true
		elif a == "--no-people":
			capture["no_people"] = true
		elif a == "--no-fx":
			capture["no_fx"] = true
		elif a.begins_with("--quality="):
			capture["quality"] = a.substr(10)
		elif a.begins_with("--time="):
			capture["time"] = float(a.substr(7))
		elif a.begins_with("--roofs="):
			capture["roofs"] = a.substr(8)


func _make_environment() -> void:
	var we := WorldEnvironment.new()
	env = Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	sky_mat = ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.32, 0.52, 0.85)
	sky_mat.sky_horizon_color = Color(0.72, 0.8, 0.9)
	sky_mat.ground_horizon_color = Color(0.6, 0.65, 0.7)
	sky_mat.ground_bottom_color = Color(0.25, 0.28, 0.3)
	sky_mat.sun_angle_max = 30.0
	sky.sky_material = sky_mat
	# éclairage du ciel recalculé progressivement (et non à chaque image : très coûteux)
	sky.process_mode = Sky.PROCESS_MODE_INCREMENTAL
	sky.radiance_size = Sky.RADIANCE_SIZE_64
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.8
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 1.0
	env.tonemap_white = 6.0
	env.ssao_enabled = true
	env.ssao_radius = 1.2
	env.ssao_intensity = 1.6
	env.glow_enabled = true
	env.glow_intensity = 0.5
	env.glow_bloom = 0.05
	env.fog_enabled = true
	env.fog_light_color = Color(0.7, 0.78, 0.88)
	env.fog_density = 0.0016
	env.fog_aerial_perspective = 0.6
	env.fog_sky_affect = 0.3
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.08
	we.environment = env
	add_child(we)
	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	sun.directional_shadow_max_distance = 110.0
	sun.light_angular_distance = 0.6
	sun.shadow_blur = 1.2
	add_child(sun)
	# préréglages : --quality=low | medium (défaut) | high
	var q: String = capture.get("quality", "medium")
	shadow_quality = q
	var vp := get_viewport()
	if q == "low":
		shadow_lights = 0
		sun.shadow_enabled = false
		env.ssao_enabled = false
		env.glow_enabled = false
		vp.scaling_3d_scale = 0.6
	elif q == "medium":
		env.ssao_enabled = false
		vp.scaling_3d_scale = 0.7
	elif q == "high":
		shadow_lights = 4
		vp.scaling_3d_scale = 1.0
		sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
		sun.directional_shadow_max_distance = 150.0
		vp.msaa_3d = Viewport.MSAA_2X
	moon = DirectionalLight3D.new()
	moon.light_color = Color(0.55, 0.65, 1.0)
	moon.light_energy = 0.0
	moon.shadow_enabled = false
	moon.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY
	add_child(moon)


# ---------------------------------------------------------------- réseau
func _on_init(d: Dictionary) -> void:
	for p in persons.values():
		p.queue_free()
	for a in animals.values():
		a.queue_free()
	persons.clear()
	animals.clear()
	for c in terrain.get_children():
		c.queue_free()
	for c in buildings.get_children():
		c.queue_free()
	terrain.chunks.clear()
	buildings.wall_chunks.clear()
	buildings.items.clear()
	buildings.blocks.clear()
	buildings.roofs.clear()
	day_length = d.get("day_length", 1200)
	night_fraction = d.get("night_fraction", 0.35)
	tick_dt = 1.0 / maxf(1, d.get("tps", 2))
	terrain.setup(d)
	buildings.setup(terrain, d)
	for info in d["people"]:
		people_info[int(info["id"])] = info
	sites = d.get("sites", [])
	for a in d["agents"]:
		_update_person(a)
	if not world_ready:
		world_ready = true
		var c := _village_center()
		cam_rig.target = c
		cam_rig.dist = 75.0
		if capture.has("cam"):
			var v: Array = capture["cam"]
			cam_rig.target = Vector3(float(v[0]), float(v[1]), float(v[2]))
			cam_rig.yaw = float(v[3])
			cam_rig.pitch = float(v[4])
			cam_rig.dist = float(v[5])
		if capture.has("roofs"):
			buildings.set_roof_mode(capture["roofs"])
	_build_minimap_base()
	_apply_debug_flags()
	hud.add_events(["🌍 Connecté à la simulation (%s)." % d.get("model", "?")])


func _apply_debug_flags() -> void:
	var args := OS.get_cmdline_user_args()
	for ch in terrain.get_children():
		for c in ch.get_children():
			if c is MultiMeshInstance3D and "--dbg-noveg" in args:
				c.visible = false
			if c is MeshInstance3D and "--dbg-noterrain" in args:
				c.visible = false
			if c is MeshInstance3D and ch == terrain and "--dbg-nowater" in args:
				c.visible = false
		if ch is MeshInstance3D and "--dbg-nowater" in args:
			ch.visible = false
	if "--dbg-noshadow" in args:
		sun.shadow_enabled = false
	if "--dbg-nobuild" in args:
		buildings.visible = false
	if "--dbg-noglow" in args:
		env.glow_enabled = false
		env.fog_enabled = false


func _village_center() -> Vector3:
	var s := Vector3.ZERO
	var n := 0
	for p in persons.values():
		s += p.global_position
		n += 1
	return s / maxf(n, 1)


func _on_tick(d: Dictionary) -> void:
	if not world_ready:
		return
	var tt := Time.get_ticks_usec()
	_on_tick_inner(d)
	prof["tick"] = prof.get("tick", 0) + Time.get_ticks_usec() - tt
	prof["ticks"] = prof.get("ticks", 0) + 1


func _on_tick_inner(d: Dictionary) -> void:
	var now := Time.get_ticks_msec() / 1000.0
	var tps := float(d.get("tps", 2))
	tick_dt = 1.0 / maxf(tps, 0.5)
	if d.get("paused", false):
		tick_dt = 1.0
	last_tick_time = now
	last_tick = d
	paused = d.get("paused", false)
	if d.has("people") and d["people"] != null:
		for info in d["people"]:
			people_info[int(info["id"])] = info
	if d.has("sites"):
		sites = d["sites"]
	for c in d.get("cells", []):
		terrain.update_cell(c)
		buildings.update_cell(c)
	var seen := {}
	for a in d.get("agents", []):
		_update_person(a)
		seen[int(a["id"])] = true
	var aseen := {}
	for a in d.get("animals", []):
		var aid := int(a[0])
		aseen[aid] = true
		if capture.has("no_animals"):
			continue
		if not animals.has(aid):
			var an := Animal3D.new()
			add_child(an)
			an.setup(aid, a[1], self)
			animals[aid] = an
		animals[aid].apply(a, tick_dt)
	for aid in animals.keys():
		if not aseen.has(aid):
			animals[aid].queue_free()
			animals.erase(aid)
	hud.add_events(d.get("events", []))
	var alive := 0
	for p in persons.values():
		if p.alive:
			alive += 1
	hud.update_top(d, alive, ["Vue aérienne", "Visiteur", "Suivi"][cam_rig.mode])
	if selected:
		hud.show_person(selected)


func _update_person(a: Dictionary) -> void:
	if capture.has("no_people"):
		return
	var pid := int(a["id"])
	if not persons.has(pid):
		if not people_info.has(pid):
			return
		var p := Person.new()
		add_child(p)
		p.setup(people_info[pid], self)
		persons[pid] = p
	persons[pid].apply(a, tick_dt)


# ---------------------------------------------------------------- requêtes du monde
func floor_height(px: float, pz: float) -> float:
	if terrain.w == 0:
		return 0.0
	var tx := int(px / T)
	var tz := int(pz / T)
	var k := Vector2i(tx, tz)
	if buildings.floor_h.has(k):
		return buildings.floor_h[k]
	return terrain.height_at(px, pz)


func item_yaw(k: Vector2i, fallback: float) -> float:
	if buildings.items.has(k):
		return buildings.items[k].rotation.y
	return fallback


## Le visiteur peut-il marcher ici ? (pas dans les murs, pas dans l'eau profonde)
func walkable(px: float, pz: float) -> bool:
	if terrain.w == 0:
		return true
	var tx := int(floor(px / T))
	var tz := int(floor(pz / T))
	if tx < -20 or tz < -20 or tx > terrain.w + 20 or tz > terrain.h + 20:
		return false
	if tx < 0 or tz < 0 or tx >= terrain.w or tz >= terrain.h:
		return true
	var k := Vector2i(tx, tz)
	if buildings.blocks.has(k):
		var bt: String = buildings.blocks[k][0]
		if bt in Buildings.WALLS or bt == "fence":
			# les murs sont fins : on ne bloque que près de l'axe du mur
			var lx := px - (tx * T + T / 2)
			var lz := pz - (tz * T + T / 2)
			var conn_x := _wallish(k + Vector2i(1, 0)) or _wallish(k + Vector2i(-1, 0))
			var conn_z := _wallish(k + Vector2i(0, 1)) or _wallish(k + Vector2i(0, -1))
			var r := Buildings.TH / 2 + 0.25
			if absf(lx) < r and absf(lz) < r:
				return false
			if conn_x and absf(lz) < r:
				return false
			if conn_z and absf(lx) < r:
				return false
			return true
	if terrain.feature[terrain.idx(tx, tz)] >= Terrain.F.ROCK and terrain.feature[terrain.idx(tx, tz)] <= Terrain.F.DIAMOND and terrain._is_mountain(tx, tz):
		return terrain.height_at(px, pz) < 1.6
	return terrain.height_at(px, pz) > -0.75


func _wallish(k: Vector2i) -> bool:
	return buildings.blocks.has(k) and buildings._is_wallish(buildings.blocks[k][0])


# ---------------------------------------------------------------- boucle
func _process(delta: float) -> void:
	if not world_ready:
		if capture.has("path") and capture.has("noworld"):
			capture_t += delta
			if capture_t > 6.0:
				var vrid := get_viewport().get_viewport_rid()
				print("NOWORLD FPS ", Engine.get_frames_per_second(), " GPU ms ", RenderingServer.viewport_get_measured_render_time_gpu(vrid))
				get_tree().quit()
		return
	var t0 := Time.get_ticks_usec()
	terrain.flush(2)
	var t1 := Time.get_ticks_usec()
	buildings.flush(3)
	var t2 := Time.get_ticks_usec()
	daylight_timer -= delta
	if daylight_timer <= 0:
		daylight_timer = 0.25
		_update_daylight(delta)
	_update_lights(delta)
	var t3 := Time.get_ticks_usec()
	prof["terrain"] = prof.get("terrain", 0) + t1 - t0
	prof["buildings"] = prof.get("buildings", 0) + t2 - t1
	prof["light"] = prof.get("light", 0) + t3 - t2
	prof["frames"] = prof.get("frames", 0) + 1
	# toits : on cache celui du bâtiment où se trouve la caméra / la personne suivie
	var focus := []
	if cam_rig.mode == CameraRig.Mode.VISITOR:
		focus.append(Vector2i(int(cam_rig.position.x / T), int(cam_rig.position.z / T)))
	if cam_rig.mode == CameraRig.Mode.FOLLOW and cam_rig.follow_node:
		var fp := cam_rig.follow_node.global_position
		focus.append(Vector2i(int(fp.x / T), int(fp.z / T)))
	buildings.set_focus_tiles(focus)
	if cam_rig.mode != CameraRig.Mode.VISITOR and cam_rig.dist < 50:
		buildings.set_cutaway(cam_rig.target, clampf(70.0 - cam_rig.dist, 20.0, 50.0))
	else:
		buildings.set_cutaway(Vector3.ZERO, 0.0)
	var tiles := {}
	for p in persons.values():
		if p.alive:
			tiles[Vector2i(int(p.global_position.x / T), int(p.global_position.z / T))] = true
	if cam_rig.mode == CameraRig.Mode.VISITOR:
		tiles[Vector2i(int(cam_rig.position.x / T), int(cam_rig.position.z / T))] = true
	buildings.animate_doors(tiles, delta)
	if selected and is_instance_valid(selected):
		_update_plumbob(delta)
	minimap_timer -= delta
	if minimap_timer <= 0:
		minimap_timer = 1.0
		_update_minimap()
		var cp := cam_rig.position if cam_rig.mode == CameraRig.Mode.VISITOR else cam_rig.target
		terrain.update_tree_shadows(cp, {"low": 0.0, "medium": 35.0, "high": 80.0}.get(shadow_quality, 35.0))
		_auto_quality(1.0)
	if capture.has("path"):
		capture_t += delta
		if capture.has("select") and selected == null and persons.has(capture["select"]):
			_select(persons[capture["select"]])
			if capture.get("mode", "") == "follow":
				cam_rig.follow(selected)
		if capture.get("mode", "") == "visitor" and cam_rig.mode != CameraRig.Mode.VISITOR and capture_t > 1.0:
			cam_rig.set_mode(CameraRig.Mode.VISITOR)
			if capture.has("cam"):
				var v: Array = capture["cam"]
				cam_rig.position = Vector3(float(v[0]), float(v[1]), float(v[2]))
				cam_rig.look_yaw = float(v[3])
				cam_rig.look_pitch = float(v[4])
		if capture_t > capture.get("after", 8.0):
			print("PROF ", prof)
			var vrid := get_viewport().get_viewport_rid()
			print("GPU ms ", RenderingServer.viewport_get_measured_render_time_gpu(vrid), " CPU render ms ", RenderingServer.viewport_get_measured_render_time_cpu(vrid), " total cpu ", RenderingServer.get_frame_setup_time_cpu())
			print("FPS ", Engine.get_frames_per_second(), " prims ", Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME), " draws ", Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME), " objs ", Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME), " process ", Performance.get_monitor(Performance.TIME_PROCESS))
			get_viewport().get_texture().get_image().save_png(capture["path"])
			print("capture : ", capture["path"])
			get_tree().quit()


## Qualité automatique : si l'image est saccadée au début, on allège le rendu.
var _aq_time := 0.0
var _aq_samples := []
func _auto_quality(dt: float) -> void:
	if capture.has("quality") or shadow_quality == "low":
		return
	_aq_time += dt
	if _aq_time < 6.0 or _aq_time > 20.0:
		return
	_aq_samples.append(Engine.get_frames_per_second())
	if _aq_samples.size() >= 5:
		var avg := 0.0
		for v in _aq_samples:
			avg += v
		avg /= _aq_samples.size()
		_aq_samples.clear()
		if avg < 20:
			shadow_quality = "low"
			get_viewport().scaling_3d_scale = 0.55
			sun.directional_shadow_max_distance = 60.0
			env.glow_enabled = false
			shadow_lights = 0
			hud.add_events(["⚙ Qualité graphique réduite automatiquement (%d i/s). Lancez avec --quality=high pour forcer." % int(avg)])


func _day_frac() -> float:
	if capture.has("time"):
		return capture["time"]
	var tick: int = last_tick.get("tick", 0)
	var since := (Time.get_ticks_msec() / 1000.0 - last_tick_time) / tick_dt if not paused else 0.0
	return fposmod((tick + minf(since, 1.0)) / float(day_length), 1.0)


func _update_daylight(_delta: float) -> void:
	# le jour commence à 6h ; la nuit occupe la fin de la journée (comme dans la simulation)
	var frac := _day_frac()
	var day_part := 1.0 - night_fraction
	var sun_t := frac / day_part  # 0 = lever, 1 = coucher
	var elev := sin(clampf(sun_t, 0.0, 1.0) * PI)
	var is_day := sun_t <= 1.0
	var az := lerpf(-1.2, 1.2, clampf(sun_t, 0, 1))
	sun.rotation = Vector3(-maxf(elev, 0.02) * 1.25 - 0.05, az + 0.6, 0)
	var warm := 1.0 - clampf(elev * 2.2, 0.0, 1.0)
	sun.light_color = Color(1.0, 0.95, 0.88).lerp(Color(1.0, 0.55, 0.3), warm)
	sun.light_energy = (smoothstep(0.0, 0.18, elev) * 1.35) if is_day else 0.0
	sun.visible = sun.light_energy > 0.01
	var night_t := 0.0
	if not is_day:
		night_t = (frac - day_part) / night_fraction
	var moon_up := sin(night_t * PI) if not is_day else 0.0
	moon.light_energy = 0.12 + moon_up * 0.3
	moon.rotation = Vector3(-0.3 - moon_up * 0.9, -1.0 + night_t * 2.0, 0)
	var dark := 1.0 - smoothstep(0.0, 0.25, elev) if is_day else 1.0
	sky_mat.sky_top_color = Color(0.32, 0.52, 0.85).lerp(Color(0.02, 0.03, 0.08), dark)
	sky_mat.sky_horizon_color = Color(0.72, 0.8, 0.9).lerp(Color(0.95, 0.55, 0.35), warm * (1.0 - dark) * 0.9).lerp(Color(0.05, 0.06, 0.12), dark)
	sky_mat.ground_horizon_color = sky_mat.sky_horizon_color.darkened(0.2)
	env.ambient_light_energy = lerpf(0.85, 0.32, dark)
	env.fog_light_color = sky_mat.sky_horizon_color
	env.tonemap_exposure = lerpf(1.0, 1.35, dark)


func _update_lights(delta: float) -> void:
	flicker_t += delta
	var night := float(last_tick.get("dark", 0.0))
	var cp := cam_rig.cam.global_position
	var cands := []
	for k in buildings.lights:
		var l: Array = buildings.lights[k]
		var d: float = (l[0] as Vector3).distance_squared_to(cp)
		if d < 120.0 * 120.0:
			cands.append([d, l, k])
	cands.sort_custom(func(a, b): return a[0] < b[0])
	# le jour, les feux n'éclairent presque rien : on économise
	var n_active := cands.size() if night > 0.15 else mini(cands.size(), 6)
	for i in light_pool.size():
		var ol: OmniLight3D = light_pool[i]
		ol.shadow_enabled = night > 0.5 and i < shadow_lights
		if i < n_active:
			var l: Array = cands[i][1]
			var k: Vector2i = cands[i][2]
			ol.visible = true
			ol.global_position = l[0]
			ol.omni_range = l[1] * 2.2
			ol.light_color = l[2]
			var fire: bool = l[3] in ["campfire", "torch", "furnace"]
			var fl := (0.85 + 0.15 * sin(flicker_t * 13.0 + k.x * 3.1) * sin(flicker_t * 7.3 + k.y)) if fire else 1.0
			ol.light_energy = (0.6 + night * 1.6) * fl
		else:
			ol.visible = false


func _update_plumbob(delta: float) -> void:
	var pb: MeshInstance3D = selected.get_node_or_null("Plumbob")
	if pb == null:
		pb = Effects.plumbob()
		pb.name = "Plumbob"
		selected.add_child(pb)
	pb.global_position = selected.head_position() + Vector3(0, 0.45 + sin(Time.get_ticks_msec() * 0.003) * 0.06, 0)
	pb.rotate_y(delta * 1.6)
	var mood: float = selected.data.get("mood", 70) / 100.0
	var c := Color(0.9, 0.2, 0.15).lerp(Color(1.0, 0.85, 0.1), clampf(mood * 2, 0, 1)).lerp(Color(0.2, 0.95, 0.3), clampf(mood * 2 - 1, 0, 1))
	var m: StandardMaterial3D = pb.material_override
	m.albedo_color = Color(c.r, c.g, c.b, 0.85)
	m.emission = c * 0.8


# ---------------------------------------------------------------- minicarte
func _build_minimap_base() -> void:
	minimap_base = Image.create(terrain.w, terrain.h, false, Image.FORMAT_RGB8)
	for y in terrain.h:
		for x in terrain.w:
			minimap_base.set_pixel(x, y, _map_color(x, y))


func _map_color(x: int, y: int) -> Color:
	var i := terrain.idx(x, y)
	var g := terrain.ground[i]
	var f := terrain.feature[i]
	var c := Color(0.38, 0.6, 0.3)
	match g:
		Terrain.G.WATER: c = Color(0.2, 0.42, 0.7)
		Terrain.G.SAND: c = Color(0.86, 0.8, 0.6)
		Terrain.G.FARMLAND: c = Color(0.45, 0.3, 0.18)
		Terrain.G.STONE_FLOOR, Terrain.G.GRAVEL: c = Color(0.5, 0.5, 0.5)
	if f == Terrain.F.TREE:
		c = Color(0.16, 0.38, 0.18)
	elif f >= Terrain.F.ROCK and f <= Terrain.F.DIAMOND:
		c = Color(0.42, 0.42, 0.44)
	var k := Vector2i(x, y)
	if buildings.blocks.has(k):
		c = Color(0.75, 0.55, 0.35)
	if buildings.roofs.has(k):
		c = Color(0.7, 0.35, 0.25)
	return c


func _update_minimap() -> void:
	if minimap_base == null:
		return
	var img := minimap_base.duplicate()
	for k in buildings.blocks:
		if k.x < terrain.w and k.y < terrain.h:
			img.set_pixel(k.x, k.y, Color(0.75, 0.55, 0.35))
	for k in buildings.roofs:
		if k.x < terrain.w and k.y < terrain.h:
			img.set_pixel(k.x, k.y, Color(0.7, 0.35, 0.25))
	for p in persons.values():
		if p.alive:
			var px := int(p.global_position.x / T)
			var py := int(p.global_position.z / T)
			for dy in [-1, 0, 1]:
				for dx in [-1, 0, 1]:
					var xx: int = clampi(px + dx, 0, terrain.w - 1)
					var yy: int = clampi(py + dy, 0, terrain.h - 1)
					img.set_pixel(xx, yy, Color(1, 1, 0.3) if p == selected else Color(1, 1, 1))
	var cp := cam_rig.target if cam_rig.mode != CameraRig.Mode.VISITOR else cam_rig.position
	var cx := clampi(int(cp.x / T), 0, terrain.w - 1)
	var cy := clampi(int(cp.z / T), 0, terrain.h - 1)
	for i in range(-3, 4):
		img.set_pixel(clampi(cx + i, 0, terrain.w - 1), cy, Color(1, 0.2, 0.2))
		img.set_pixel(cx, clampi(cy + i, 0, terrain.h - 1), Color(1, 0.2, 0.2))
	var big := img.duplicate()
	big.resize(terrain.w * 2, terrain.h * 2, Image.INTERPOLATE_NEAREST)
	hud.update_minimap(big)


func jump_to_uv(uv: Vector2) -> void:
	var p := Vector3(uv.x * terrain.w * T, 0, uv.y * terrain.h * T)
	if cam_rig.mode == CameraRig.Mode.VISITOR:
		cam_rig.position = p
	else:
		cam_rig.mode = CameraRig.Mode.AERIAL
		cam_rig.target = p


# ---------------------------------------------------------------- entrées
func _unhandled_input(ev: InputEvent) -> void:
	if ev is InputEventKey and ev.pressed and not ev.echo:
		match ev.keycode:
			KEY_V:
				ui_action("visitor" if cam_rig.mode != CameraRig.Mode.VISITOR else "aerial")
			KEY_F:
				ui_action("follow")
			KEY_R:
				ui_action("roofs")
			KEY_H:
				hud.toggle_help()
			KEY_TAB:
				_select_next()
			KEY_SPACE:
				net.send({"cmd": "pause", "value": not paused})
			KEY_1: set_speed(0)
			KEY_2: set_speed(2)
			KEY_3: set_speed(6)
			KEY_4: set_speed(20)
			KEY_ESCAPE:
				if cam_rig.mode != CameraRig.Mode.VISITOR:
					_select(null)
	elif ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		if cam_rig.mode == CameraRig.Mode.VISITOR and cam_rig.mouse_captured:
			_pick(get_viewport().get_visible_rect().size / 2)
		else:
			_pick(ev.position)


func _pick(screen: Vector2) -> void:
	var cam := cam_rig.cam
	var best: Person = null
	var bd := 60.0
	for p in persons.values():
		if not p.alive or not p.visible:
			continue
		for h in [0.4, 1.0, 1.6]:
			var wp: Vector3 = p.global_position + Vector3(0, h, 0)
			if cam.is_position_behind(wp):
				continue
			var d := cam.unproject_position(wp).distance_to(screen)
			if d < bd:
				bd = d
				best = p
	if best:
		_select(best)


func _select(p: Person) -> void:
	if selected and is_instance_valid(selected):
		var pb := selected.get_node_or_null("Plumbob")
		if pb:
			pb.queue_free()
	selected = p
	hud.show_person(p)


func _select_next() -> void:
	var ids := persons.keys()
	ids.sort()
	var alive := ids.filter(func(i): return persons[i].alive)
	if alive.is_empty():
		return
	var i := 0
	if selected:
		i = (alive.find(selected.id) + 1) % alive.size()
	_select(persons[alive[i]])
	if cam_rig.mode == CameraRig.Mode.FOLLOW:
		cam_rig.follow(selected)
	else:
		cam_rig.focus_on(selected.global_position)


func set_speed(tps: int) -> void:
	if tps <= 0:
		net.send({"cmd": "pause", "value": true})
	else:
		net.send({"cmd": "pause", "value": false})
		net.send({"cmd": "speed", "tps": tps})


func ui_action(what: String) -> void:
	match what:
		"aerial":
			cam_rig.set_mode(CameraRig.Mode.AERIAL)
		"visitor":
			cam_rig.set_mode(CameraRig.Mode.VISITOR)
		"roofs":
			var order := ["auto", "on", "off"]
			buildings.set_roof_mode(order[(order.find(buildings.roof_mode) + 1) % 3])
			hud.add_events(["Toits : " + {"auto": "automatiques", "on": "toujours visibles", "off": "cachés"}[buildings.roof_mode]])
		"follow":
			if selected:
				cam_rig.follow(selected)
		"goto":
			if selected:
				cam_rig.set_mode(CameraRig.Mode.AERIAL)
				cam_rig.target = selected.global_position
				cam_rig.dist = 16.0
		"close":
			_select(null)
