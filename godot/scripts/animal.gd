class_name Animal3D
extends Node3D
## Un animal : modèle animé, déplacement lissé, petit trot procédural si le
## modèle n'a pas d'animation de marche.

const SPECIES := {
	# chemin, taille (plus grande dimension), anim repos, anim marche, anim course, décalage d'orientation
	"cow": ["res://assets/animals/Cow.fbx", 2.0, "Armature|Idle", "Armature|Walk", "Armature|Run", 0.0],
	"sheep": ["res://assets/animals/Sheep.fbx", 1.25, "Armature|Idle", "", "", 0.0],
	"pig": ["res://assets/animals/Pig.fbx", 1.15, "Armature|Idle", "", "", 0.0],
	"chicken": ["res://assets/animals/Chick.fbx", 0.45, "Armature|ArmatureAction_002", "", "", 0.0],
	"wolf": ["res://assets/animals/Wolf.fbx", 1.4, "WolfArmature|Idle", "WolfArmature|Walking", "WolfArmature|Walking", 0.0],
}

var id := 0
var species := ""
var model: Node3D
var inner: Node3D
var ap: AnimationPlayer
var spec: Array
var from_pos := Vector3.ZERO
var to_pos := Vector3.ZERO
var move_t := 1.0
var move_dur := 0.5
var tile := Vector2i(-1, -1)
var yaw := 0.0
var adult := true
var phase := 0.0
var world: Node
var cur := ""


func setup(aid: int, sp: String, w: Node) -> void:
	id = aid
	species = sp
	world = w
	spec = SPECIES.get(sp, SPECIES["sheep"])
	model = Assets.fitted(spec[0], spec[1])
	for n in model.find_children("*", "Light3D", true, false) + model.find_children("*", "Camera3D", true, false):
		n.queue_free()
	add_child(model)
	var aps := model.find_children("*", "AnimationPlayer", true, false)
	if aps.size() > 0:
		ap = aps[0]
	phase = randf() * TAU


func apply(a: Array, tick_dt: float) -> void:
	# [id, espèce, x, y, adulte, bouge, fuit, maître, laisse]
	var nt := Vector2i(a[2], a[3])
	var target := Assets.tile_to_world(nt.x, nt.y) + Vector3(sin(id * 1.7) * 0.4, 0, cos(id * 2.3) * 0.4)
	var was_adult := adult
	adult = a[4] == 1
	if was_adult != adult or tile.x < 0:
		model.scale = Vector3.ONE * (1.0 if adult else 0.55)
	if nt != tile:
		if tile.x < 0 or global_position.distance_to(target) > Assets.T * 4:
			global_position = target
			from_pos = target
			to_pos = target
			move_t = 1.0
		else:
			from_pos = Vector3(global_position.x, 0, global_position.z)
			to_pos = target
			move_t = 0.0
			move_dur = maxf(0.08, tick_dt * (2.0 if a[6] == 0 else 1.0))
		tile = nt


func _process(delta: float) -> void:
	if world == null:
		return
	if move_t < 1.0:
		move_t = minf(1.0, move_t + delta / move_dur)
	var p := from_pos.lerp(to_pos, move_t)
	var moving := move_t < 1.0 and from_pos.distance_to(to_pos) > 0.05
	phase += delta
	var bob := 0.0
	if moving and spec[3] == "":
		bob = absf(sin(phase * 11.0)) * 0.08 * (1.0 if adult else 0.6)
	global_position = Vector3(p.x, world.floor_height(p.x, p.z) + bob, p.z)
	if moving:
		var d := to_pos - from_pos
		yaw = lerp_angle(yaw, atan2(d.x, d.z) + spec[5], minf(1.0, delta * 8.0))
	rotation.y = yaw
	if ap:
		var want: String = spec[2]
		if moving and spec[3] != "":
			want = spec[3]
		if want != "" and ap.has_animation(want) and cur != want:
			cur = want
			var anim := ap.get_animation(want)
			anim.loop_mode = Animation.LOOP_LINEAR
			ap.play(want, 0.3)
