class_name Person
extends Node3D
## Un habitant en 3D : modèle habillé, animations réalistes, déplacements lissés,
## outil en main selon l'activité, orientation vers ce qu'il fait.

const T := Assets.T

# activité de la simulation -> [animation, boucle, outil par défaut]
const ACT := {
	"idle": ["idle", true, ""], "walk": ["walk", true, ""],
	"chop": ["swing", false, "axe"], "mine": ["swing", false, "pickaxe"], "dig": ["kneel_work", true, "shovel"],
	"pick": ["pickup", false, ""], "harvest": ["pickup", false, ""], "plant": ["kneel_work", true, ""],
	"farm": ["swing", false, "hoe"], "build": ["swing", false, "hammer"], "craft": ["counter", true, "hammer"],
	"fight": ["attack", false, "sword"], "eat": ["drink", false, ""], "eat_seated": ["sit_nod", true, ""],
	"sit": ["sit", true, ""], "read": ["look", true, ""], "sleep": ["lie", true, ""], "sleep_bed": ["lie", true, ""],
	"sit_ground": ["ground_sit", true, ""], "dance": ["dance", true, ""], "celebrate": ["celebrate", false, ""],
	"cry": ["cry", true, ""], "idle_look": ["look", true, ""], "talk": ["talk", true, ""], "give": ["give", false, ""],
	"dress": ["interact", false, ""], "drink": ["drink", false, ""], "fish": ["guard", true, "fishing_rod"],
}
const TOOLS := {
	"axe": ["res://assets/props/Axe.fbx", 0.75], "pickaxe": ["res://assets/props/Hammer_Double.fbx", 0.75],
	"shovel": ["res://assets/props/Spear.fbx", 1.3], "hoe": ["res://assets/props/Scythe.fbx", 1.3],
	"hammer": ["res://assets/props/Hammer_Small.fbx", 0.45], "sword": ["res://assets/props/Sword.fbx", 0.95],
	"spear": ["res://assets/props/Spear.fbx", 1.6], "bow": ["res://assets/props/Bow_Wooden.fbx", 1.0],
	"fishing_rod": ["res://assets/props/WoodenStaff.fbx", 1.8], "shield": ["res://assets/props/Shield_Round.fbx", 0.6],
}

var id := 0
var pname := ""
var gender := "m"
var color := Color.WHITE
var outfit := -1
var data := {}
var alive := true
var model: Node3D
var ap: AnimationPlayer
var skel: Skeleton3D
var hand: BoneAttachment3D
var tool_name := ""
var tool_node: Node3D
var cur_anim := ""
var anim_cool := 0.0
var from_pos := Vector3.ZERO
var to_pos := Vector3.ZERO
var move_t := 1.0
var move_dur := 0.5
var speed := 0.0
var tile := Vector2i(-1, -1)
var yaw := 0.0
var lift := 0.0           # hauteur supplémentaire (lit, chaise)
var lie_tilt := 0.0
var world: Node           # main (accès terrain / bâtiments)
var dead_time := 0.0


func setup(info: Dictionary, w: Node) -> void:
	id = info["id"]
	pname = info["name"]
	gender = info.get("gender", "m")
	var c: Array = info.get("color", [255, 255, 255])
	color = Color8(c[0], c[1], c[2])
	world = w


func _load_model(o: int) -> void:
	if model:
		model.queue_free()
	outfit = o
	model = Assets.scene(Assets.character_path(gender, o)).instantiate()
	add_child(model)
	ap = model.find_children("*", "AnimationPlayer", true, false)[0]
	if not ap.has_animation_library("ual"):
		ap.add_animation_library("ual", Assets.animations())
	skel = model.find_children("*", "Skeleton3D", true, false)[0]
	hand = BoneAttachment3D.new()
	skel.add_child(hand)
	hand.bone_name = "Wrist.R"
	for mi in model.find_children("*", "MeshInstance3D", true, false):
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	cur_anim = ""
	tool_name = ""
	tool_node = null


func apply(d: Dictionary, tick_dt: float) -> void:
	data = d
	if d.get("outfit", 0) != outfit:
		_load_model(d.get("outfit", 0))
	var was_alive := alive
	alive = d.get("alive", true)
	if not alive and was_alive:
		dead_time = 0.0
	var seat = d.get("seat")
	var nt := Vector2i(d["x"], d["y"])
	var target := Assets.tile_to_world(nt.x, nt.y)
	lift = 0.0
	if seat != null:
		target = Assets.tile_to_world(seat[0], seat[1])
		nt = Vector2i(seat[0], seat[1])
	if nt != tile or to_pos.distance_to(target) > 0.01:
		var cur := global_position if move_t < 1.0 or tile.x >= 0 else target
		if tile.x < 0 or cur.distance_to(target) > T * 4:
			from_pos = target
			to_pos = target
			move_t = 1.0
			global_position = target
		else:
			from_pos = Vector3(cur.x, 0, cur.z)
			to_pos = target
			move_t = 0.0
			move_dur = maxf(0.05, tick_dt * (1.0 if not d.get("mv", false) else 1.02))
		tile = nt


func _process(delta: float) -> void:
	if model == null or world == null:
		return
	if not alive:
		dead_time += delta
		_play("death", false)
		visible = dead_time < 60.0
		return
	# déplacement lissé d'une case à l'autre
	var prev := global_position
	if move_t < 1.0:
		move_t = minf(1.0, move_t + delta / move_dur)
	var p := from_pos.lerp(to_pos, move_t)
	var moving := move_t < 1.0 and from_pos.distance_to(to_pos) > 0.05
	speed = from_pos.distance_to(to_pos) / move_dur if moving else 0.0
	var act: String = data.get("act", "idle")
	var seat = data.get("seat")
	var gy: float = world.floor_height(p.x, p.z)
	if not moving and seat != null and act in ["sit", "eat_seated"]:
		gy += 0.0
	elif not moving and act == "sleep_bed":
		gy += 0.55
	global_position = Vector3(p.x, gy, p.z)
	# orientation
	var want := yaw
	if moving:
		var dir := to_pos - from_pos
		want = atan2(dir.x, dir.z)
	elif seat != null and act in ["sit", "eat_seated", "sleep_bed"]:
		want = world.item_yaw(Vector2i(seat[0], seat[1]), yaw)
		if act == "eat_seated" and data.get("fx") != null:
			want = _face(data["fx"], data["fy"], want)
	elif data.get("fx") != null:
		want = _face(data["fx"], data["fy"], want)
	yaw = lerp_angle(yaw, want, minf(1.0, delta * (10.0 if moving else 5.0)))
	rotation.y = yaw
	# allongé : on couche le corps dans l'axe du lit
	model.rotation.x = 0.0
	# animation
	if moving:
		if speed > 2.6:
			_play("jog", true, clampf(speed / 3.6, 0.6, 1.8))
		else:
			_play("walk", true, clampf(speed / 1.5, 0.5, 1.8))
		_set_tool("")
	else:
		var spec: Array = ACT.get(act, ACT["idle"])
		var anim: String = spec[0]
		if act == "idle":
			var en: int = data.get("en", 80)
			if en < 20:
				anim = "tired"
			elif data.get("say", "") != "":
				anim = "talk"
		if act == "fight" and data.get("tool", "") == "":
			anim = "punch"
		var tl: String = data.get("tool", "") if data.get("tool", "") != "" else spec[2]
		_set_tool(_tool_kind(tl, spec[2]))
		_play(anim, spec[1])


func _face(fx: int, fy: int, fallback: float) -> float:
	var t := Assets.tile_to_world(fx, fy)
	var d := t - global_position
	if Vector2(d.x, d.z).length() < 0.1:
		return fallback
	return atan2(d.x, d.z)


func _play(anim: String, loop: bool, spd := 1.0) -> void:
	var full := "ual/" + anim
	if not ap.has_animation(full):
		full = "ual/idle"
	ap.speed_scale = spd
	if cur_anim != full:
		cur_anim = full
		ap.play(full, 0.25)
		anim_cool = 0.0
	elif not loop and not ap.is_playing():
		# geste de travail répété (coup de hache, cueillette...) avec une petite pause
		anim_cool += get_process_delta_time()
		if anim_cool > 0.15:
			anim_cool = 0.0
			ap.play(full, 0.15)
			ap.seek(0.0, true)


func _tool_kind(name: String, default: String) -> String:
	if name == "":
		return default
	for k in ["pickaxe", "axe", "shovel", "hoe", "hammer", "sword", "spear", "bow", "fishing_rod"]:
		if k in name:
			return k
	return default


func _set_tool(kind: String) -> void:
	if kind == tool_name:
		return
	tool_name = kind
	if tool_node:
		tool_node.queue_free()
		tool_node = null
	if kind == "" or not TOOLS.has(kind):
		return
	var spec: Array = TOOLS[kind]
	tool_node = Assets.fitted(spec[0], spec[1], "max")
	# le manche dans l'axe de la main
	tool_node.rotation_degrees = Vector3(0, 0, -90)
	tool_node.position = Vector3(0.0, 0.08, 0.0)
	hand.add_child(tool_node)


func head_position() -> Vector3:
	return global_position + Vector3(0, 2.0 if data.get("act", "") not in ["sit", "eat_seated", "sit_ground"] else 1.4, 0)
