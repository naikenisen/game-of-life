extends SceneTree
## Aperçu de contrôle : affiche des personnages jouant les animations transférées
## et enregistre une capture.   godot -s tools/preview_anims.gd -- sortie.png anim1,anim2,...

var frames := 0
var out_path := "user://preview.png"
var root3d: Node3D


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() > 0:
		out_path = args[0]
	var anims := ["idle", "walk", "sit", "swing", "kneel_work", "dance", "lie", "talk"]
	if args.size() > 1:
		anims = args[1].split(",")
	root3d = Node3D.new()
	get_root().add_child(root3d)
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.6, 0.7, 0.8)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.6, 0.6, 0.65)
	env.environment = e
	root3d.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	sun.shadow_enabled = true
	root3d.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(30, 30)
	ground.mesh = pm
	root3d.add_child(ground)
	var lib: AnimationLibrary = load("res://generated/ual_library.res")
	var models := ["res://assets/characters/male/Worker.glb", "res://assets/characters/female/Witch.glb",
		"res://assets/characters/male/Farmer.glb", "res://assets/characters/female/Casual.glb"]
	for i in anims.size():
		var ch: Node3D = load(models[i % models.size()]).instantiate()
		root3d.add_child(ch)
		ch.position = Vector3((i - anims.size() / 2.0 + 0.5) * 1.15, 0, 0)
		var ap: AnimationPlayer = ch.find_children("*", "AnimationPlayer", true, false)[0]
		ap.add_animation_library("ual", lib)
		ap.play("ual/" + anims[i])
		ap.seek(0.6, true)
		var lbl := Label3D.new()
		lbl.text = anims[i]
		lbl.position = Vector3(0, 2.1, 0)
		lbl.pixel_size = 0.006
		ch.add_child(lbl)
	var cam := Camera3D.new()
	cam.position = Vector3(0, 1.0, 2.6)
	cam.rotation_degrees = Vector3(-6, 0, 0)
	root3d.add_child(cam)
	cam.current = true


func _process(_delta: float) -> bool:
	frames += 1
	if frames == 30:
		var img := get_root().get_texture().get_image()
		img.save_png(out_path)
		print("capture : ", out_path)
		return true
	return false
