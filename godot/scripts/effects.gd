class_name Effects
extends RefCounted
## Petits effets : feu, fumée, losange d'humeur (plumbob).

static var _fire_mat: StandardMaterial3D
static var _smoke_mat: StandardMaterial3D


static func _soft_tex(inner: Color, outer: Color) -> GradientTexture2D:
	var g := Gradient.new()
	g.set_color(0, inner)
	g.set_color(1, outer)
	var t := GradientTexture2D.new()
	t.gradient = g
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = Vector2(0.5, 0.5)
	t.fill_to = Vector2(0.5, 0.0)
	t.width = 64
	t.height = 64
	return t


static func fire(pos: Vector3, scale: float) -> Node3D:
	if "--no-fx" in OS.get_cmdline_user_args():
		return Node3D.new()
	if _fire_mat == null:
		_fire_mat = StandardMaterial3D.new()
		_fire_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		_fire_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_fire_mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		_fire_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		_fire_mat.vertex_color_use_as_albedo = true
		_fire_mat.albedo_texture = _soft_tex(Color(1, 0.9, 0.6, 1), Color(1, 0.3, 0.0, 0))
	var p := GPUParticles3D.new()
	p.amount = int(28 * maxf(scale, 0.4))
	p.lifetime = 0.7
	p.position = pos
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, 1, 0)
	pm.spread = 12.0
	pm.initial_velocity_min = 0.6 * scale
	pm.initial_velocity_max = 1.3 * scale
	pm.gravity = Vector3(0, 0.6, 0)
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	pm.emission_sphere_radius = 0.22 * scale
	pm.scale_min = 0.6
	pm.scale_max = 1.1
	var curve := CurveTexture.new()
	var c := Curve.new()
	c.add_point(Vector2(0, 0.6))
	c.add_point(Vector2(0.3, 1.0))
	c.add_point(Vector2(1, 0.0))
	curve.curve = c
	pm.scale_curve = curve
	var grad := Gradient.new()
	grad.set_color(0, Color(1.0, 0.85, 0.4, 1))
	grad.set_color(1, Color(0.9, 0.2, 0.05, 0))
	var gt := GradientTexture1D.new()
	gt.gradient = grad
	pm.color_ramp = gt
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.5, 0.5) * scale
	q.material = _fire_mat
	p.draw_pass_1 = q
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return p


static func smoke(pos: Vector3, scale: float) -> Node3D:
	if "--no-fx" in OS.get_cmdline_user_args():
		return Node3D.new()
	if _smoke_mat == null:
		_smoke_mat = StandardMaterial3D.new()
		_smoke_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_smoke_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		_smoke_mat.vertex_color_use_as_albedo = true
		_smoke_mat.albedo_texture = _soft_tex(Color(0.8, 0.8, 0.8, 0.5), Color(0.8, 0.8, 0.8, 0.0))
	var p := GPUParticles3D.new()
	p.amount = 14
	p.lifetime = 4.0
	p.position = pos
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0.2, 1, 0)
	pm.spread = 15.0
	pm.initial_velocity_min = 0.4
	pm.initial_velocity_max = 0.8
	pm.gravity = Vector3(0.15, 0.1, 0)
	pm.scale_min = 1.0 * scale
	pm.scale_max = 2.2 * scale
	var curve := CurveTexture.new()
	var c := Curve.new()
	c.add_point(Vector2(0, 0.3))
	c.add_point(Vector2(1, 1.0))
	curve.curve = c
	pm.scale_curve = curve
	var grad := Gradient.new()
	grad.set_color(0, Color(0.6, 0.6, 0.6, 0.45))
	grad.set_color(1, Color(0.8, 0.8, 0.8, 0.0))
	var gt := GradientTexture1D.new()
	gt.gradient = grad
	pm.color_ramp = gt
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.8, 0.8)
	q.material = _smoke_mat
	p.draw_pass_1 = q
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return p


## Le célèbre losange vert au-dessus de la tête (couleur = humeur).
static func plumbob() -> MeshInstance3D:
	var am := ArrayMesh.new()
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var top := Vector3(0, 0.32, 0)
	var bot := Vector3(0, -0.32, 0)
	var ring := []
	for i in 6:
		var a := i * TAU / 6
		ring.append(Vector3(cos(a) * 0.12, 0, sin(a) * 0.12))
	for i in 6:
		var a: Vector3 = ring[i]
		var b: Vector3 = ring[(i + 1) % 6]
		st.add_vertex(top)
		st.add_vertex(b)
		st.add_vertex(a)
		st.add_vertex(bot)
		st.add_vertex(a)
		st.add_vertex(b)
	st.generate_normals()
	am = st.commit()
	var mi := MeshInstance3D.new()
	mi.mesh = am
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.2, 0.95, 0.3, 0.85)
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.emission_enabled = true
	m.emission = Color(0.1, 0.8, 0.2)
	m.emission_energy_multiplier = 1.5
	m.roughness = 0.1
	mi.material_override = m
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi
