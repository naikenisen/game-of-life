extends SceneTree
## Outil (exécuté une fois, sans fenêtre) : transfère les animations de la
## « Universal Animation Library » de Quaternius (squelette UE) vers le squelette
## des personnages « Ultimate Modular Characters » (pieds en IK rattachés à Root).
##
## Méthode : on aligne d'abord le personnage sur la pose T de la bibliothèque
## (direction des bras/jambes), puis pour chaque image on applique au personnage,
## en espace global, la rotation de chaque os relative à la pose de référence.
## Les pieds (contrôleurs IK) sont replacés au bout des jambes calculées.
##
##   godot --headless -s tools/bake_retarget.gd

const UAL_PATH := "res://assets/animations/UAL1.glb"
const CHAR_PATH := "res://assets/characters/male/Worker.glb"
const OUT_PATH := "res://generated/ual_library.res"
const FPS := 30.0

# os du personnage <- os de la bibliothèque
const MAP := {
	"Body": "pelvis", "Hips": "pelvis", "Abdomen": "spine_01", "Torso": "spine_02", "Chest": "spine_03",
	"Neck": "neck_01", "Head": "Head",
	"Shoulder.L": "clavicle_l", "UpperArm.L": "upperarm_l", "LowerArm.L": "lowerarm_l", "Wrist.L": "hand_l",
	"Shoulder.R": "clavicle_r", "UpperArm.R": "upperarm_r", "LowerArm.R": "lowerarm_r", "Wrist.R": "hand_r",
	"Thumb1.L": "thumb_01_l", "Thumb2.L": "thumb_02_l", "Thumb3.L": "thumb_03_l",
	"Thumb1.R": "thumb_01_r", "Thumb2.R": "thumb_02_r", "Thumb3.R": "thumb_03_r",
	"Index1.L": "index_01_l", "Index2.L": "index_02_l", "Index3.L": "index_03_l",
	"Index1.R": "index_01_r", "Index2.R": "index_02_r", "Index3.R": "index_03_r",
	"Middle1.L": "middle_01_l", "Middle2.L": "middle_02_l", "Middle3.L": "middle_03_l",
	"Middle1.R": "middle_01_r", "Middle2.R": "middle_02_r", "Middle3.R": "middle_03_r",
	"Ring1.L": "ring_01_l", "Ring2.L": "ring_02_l", "Ring3.L": "ring_03_l",
	"Ring1.R": "ring_01_r", "Ring2.R": "ring_02_r", "Ring3.R": "ring_03_r",
	"Pinky1.L": "pinky_01_l", "Pinky2.L": "pinky_02_l", "Pinky3.L": "pinky_03_l",
	"Pinky1.R": "pinky_01_r", "Pinky2.R": "pinky_02_r", "Pinky3.R": "pinky_03_r",
	"UpperLeg.L": "thigh_l", "LowerLeg.L": "calf_l", "Foot.L": "foot_l",
	"UpperLeg.R": "thigh_r", "LowerLeg.R": "calf_r", "Foot.R": "foot_r",
}
# os à aligner sur la pose T : os -> os enfant qui donne sa direction
const ALIGN := {
	"UpperArm.L": "LowerArm.L", "LowerArm.L": "Wrist.L", "UpperArm.R": "LowerArm.R", "LowerArm.R": "Wrist.R",
	"UpperLeg.L": "LowerLeg.L", "UpperLeg.R": "LowerLeg.R", "LowerLeg.L": "Foot.L", "LowerLeg.R": "Foot.R",
}
const ALIGN_SRC := {
	"UpperArm.L": ["upperarm_l", "lowerarm_l"], "LowerArm.L": ["lowerarm_l", "hand_l"],
	"UpperArm.R": ["upperarm_r", "lowerarm_r"], "LowerArm.R": ["lowerarm_r", "hand_r"],
	"UpperLeg.L": ["thigh_l", "calf_l"], "UpperLeg.R": ["thigh_r", "calf_r"],
	"LowerLeg.L": ["calf_l", "foot_l"], "LowerLeg.R": ["calf_r", "foot_r"],
}
# contrôleurs IK : parent « virtuel » pour suivre la jambe
const VIRTUAL_PARENT := {"Foot.L": "LowerLeg.L", "PT.L": "LowerLeg.L", "Foot.R": "LowerLeg.R", "PT.R": "LowerLeg.R"}
# vrai pour les pieds : la rotation vient de la source, la position de la jambe
const IK_BONES := ["Foot.L", "Foot.R", "PT.L", "PT.R"]

# animations à transférer : nom source -> [nom final, boucle]
const ANIMS := {
	"Idle_Loop": ["idle", true], "Idle_Talking_Loop": ["talk", true], "Idle_LookAround_Loop": ["look", true],
	"Idle_Tired_Loop": ["tired", true], "Walk_Loop": ["walk", true], "Walk_Formal_Loop": ["walk_formal", true],
	"Jog_Fwd_Loop": ["jog", true], "Sprint_Loop": ["sprint", true],
	"Sitting_Enter": ["sit_enter", false], "Sitting_Idle_Loop": ["sit", true], "Sitting_Talking_Loop": ["sit_talk", true],
	"Sitting_Nodding_Loop": ["sit_nod", true], "Sitting_Idle02_Loop": ["sit2", true], "Sitting_Exit": ["sit_exit", false],
	"GroundSit_Enter": ["ground_enter", false], "GroundSit_Idle_Loop": ["ground_sit", true],
	"GroundSit_Exit": ["ground_exit", false],
	"Drink": ["drink", false], "Fixing_Kneeling": ["kneel_work", true], "PickUp_Kneeling": ["pickup", false],
	"PickUp_Table": ["pickup_table", false], "Interact": ["interact", false],
	"Counter_Give": ["give", false], "Counter_Show": ["show", false], "Counter_Idle_Loop": ["counter", true],
	"Sword_Attack": ["attack", false], "Sword_Attack_Standing": ["swing", false], "Sword_Idle": ["guard", true],
	"Punch_Jab": ["punch", false], "Punch_Cross": ["punch2", false], "Hit_Chest": ["hit", false],
	"Death01": ["death", false], "Dance_Loop": ["dance", true], "Celebration": ["celebrate", false],
	"Crying": ["cry", true], "Crouch_Idle_Loop": ["crouch", true], "Push_Loop": ["push", true],
	"Crawl_Idle_Loop": ["lie_idle", true], "Swim_Idle_Loop": ["swim", true], "Spell_Simple_Shoot": ["throw", false],
	"Pistol_Aim_Neutral": ["aim", true],
}

var src_sk: Skeleton3D
var dst_sk: Skeleton3D
var src_rest_g := {}   # nom -> Transform3D global (pose de repos source = pose T)
var dst_ref_g := {}    # nom -> Transform3D global de référence (personnage aligné en T)
var dst_ref_local := {}
var order := []        # os du personnage dans l'ordre hiérarchique
var ratio := 1.0


func _init() -> void:
	var src_scene = load(UAL_PATH).instantiate()
	var dst_scene = load(CHAR_PATH).instantiate()
	src_sk = src_scene.find_children("*", "Skeleton3D", true, false)[0]
	dst_sk = dst_scene.find_children("*", "Skeleton3D", true, false)[0]
	var ap: AnimationPlayer = src_scene.find_children("*", "AnimationPlayer", true, false)[0]
	_build_reference()
	var lib := AnimationLibrary.new()
	var n := 0
	for src_name in ANIMS:
		# l'import de Godot retire le suffixe « _Loop » (et règle la boucle lui-même)
		var real_name: String = src_name if ap.has_animation(src_name) else src_name.trim_suffix("_Loop")
		if not ap.has_animation(real_name):
			push_warning("animation absente : " + src_name)
			continue
		var res = _bake(ap.get_animation(real_name), ANIMS[src_name][1])
		lib.add_animation(ANIMS[src_name][0], res)
		n += 1
	# pose allongée (sommeil) : dernière image de la mort, en boucle
	var death := lib.get_animation("death")
	if death:
		var lie := _freeze_last(death)
		lib.add_animation("lie", lie)
	DirAccess.make_dir_recursive_absolute("res://generated")
	var err := ResourceSaver.save(lib, OUT_PATH, ResourceSaver.FLAG_COMPRESS)
	print("Animations transférées : %d -> %s (%s)" % [n, OUT_PATH, error_string(err)])
	src_scene.free()
	dst_scene.free()
	quit()


func _children_of(sk: Skeleton3D, b: int) -> Array:
	return sk.get_bone_children(b)


func _build_reference() -> void:
	for i in src_sk.get_bone_count():
		src_rest_g[src_sk.get_bone_name(i)] = src_sk.get_bone_global_rest(i)
	# ordre hiérarchique (parents avant enfants)
	var roots := []
	for i in dst_sk.get_bone_count():
		if dst_sk.get_bone_parent(i) < 0:
			roots.append(i)
	var stack := roots.duplicate()
	while stack.size() > 0:
		var b = stack.pop_front()
		order.append(dst_sk.get_bone_name(b))
		for c in dst_sk.get_bone_children(b):
			stack.append(c)
	# réordonne pour que chaque os vienne après son parent « virtuel » (pieds IK après les jambes)
	var sorted_order := []
	var placed := {}
	while sorted_order.size() < order.size():
		for name in order:
			if placed.has(name):
				continue
			var vp := _parent_name(name)
			if vp == "" or placed.has(vp):
				sorted_order.append(name)
				placed[name] = true
	order = sorted_order
	for name in order:
		dst_ref_g[name] = dst_sk.get_bone_global_rest(dst_sk.find_bone(name))
	# sous-arbre (y compris parents virtuels) pour propager les alignements
	var subtree := {}
	for name in order:
		subtree[name] = [name]
	for name in order:
		var p := _parent_name(name)
		while p != "":
			subtree[p].append(name)
			p = _parent_name(p)
	# alignement en pose T
	for name in order:
		if not ALIGN.has(name):
			continue
		var a: Vector3 = dst_ref_g[name].origin
		var b: Vector3 = dst_ref_g[ALIGN[name]].origin
		var sa: Vector3 = src_rest_g[ALIGN_SRC[name][0]].origin
		var sb: Vector3 = src_rest_g[ALIGN_SRC[name][1]].origin
		var q := Quaternion((b - a).normalized(), (sb - sa).normalized())
		var qb := Basis(q)
		for d in subtree[name]:
			var g: Transform3D = dst_ref_g[d]
			g.basis = qb * g.basis
			g.origin = a + qb * (g.origin - a)
			dst_ref_g[d] = g
	for name in order:
		var p := _real_parent(name)
		dst_ref_local[name] = (dst_ref_g[p].affine_inverse() * dst_ref_g[name]) if p != "" else dst_ref_g[name]
	ratio = dst_ref_g["Hips"].origin.y / src_rest_g["pelvis"].origin.y


func _real_parent(name: String) -> String:
	var p := dst_sk.get_bone_parent(dst_sk.find_bone(name))
	return dst_sk.get_bone_name(p) if p >= 0 else ""


func _parent_name(name: String) -> String:
	if VIRTUAL_PARENT.has(name):
		return VIRTUAL_PARENT[name]
	return _real_parent(name)


func _src_globals(anim: Animation, t: float) -> Dictionary:
	# pose locale de chaque os source à l'instant t, puis cumul en global
	var local := {}
	for i in src_sk.get_bone_count():
		var rest := src_sk.get_bone_rest(i)
		local[src_sk.get_bone_name(i)] = [rest.origin, rest.basis.get_rotation_quaternion(), rest.basis.get_scale()]
	for tr in anim.get_track_count():
		var path := anim.track_get_path(tr)
		var bone := path.get_concatenated_subnames()
		if not local.has(bone):
			continue
		match anim.track_get_type(tr):
			Animation.TYPE_POSITION_3D:
				local[bone][0] = anim.position_track_interpolate(tr, t)
			Animation.TYPE_ROTATION_3D:
				local[bone][1] = anim.rotation_track_interpolate(tr, t)
			Animation.TYPE_SCALE_3D:
				local[bone][2] = anim.scale_track_interpolate(tr, t)
	var g := {}
	for i in src_sk.get_bone_count():  # les parents précèdent toujours leurs enfants dans un glTF importé
		var nm := src_sk.get_bone_name(i)
		var l = local[nm]
		var xf := Transform3D(Basis(l[1]).scaled(l[2]), l[0])
		var p := src_sk.get_bone_parent(i)
		g[nm] = (g[src_sk.get_bone_name(p)] * xf) if p >= 0 else xf
	return g


func _bake(anim: Animation, loop: bool) -> Animation:
	var out := Animation.new()
	out.length = anim.length
	out.loop_mode = Animation.LOOP_LINEAR if loop else Animation.LOOP_NONE
	var rot_tracks := {}
	var pos_tracks := {}
	for name in order:
		if name == "Root":
			continue
		var path := NodePath("CharacterArmature/Skeleton3D:" + name)
		var rt := out.add_track(Animation.TYPE_ROTATION_3D)
		out.track_set_path(rt, path)
		rot_tracks[name] = rt
		if name == "Body" or name in IK_BONES:
			var pt := out.add_track(Animation.TYPE_POSITION_3D)
			out.track_set_path(pt, path)
			pos_tracks[name] = pt
	var frames := maxi(1, int(ceil(anim.length * FPS)))
	for f in frames + 1:
		var t := minf(f / FPS, anim.length)
		var sg := _src_globals(anim, t)
		var dg := {}
		for name in order:
			var ref: Transform3D = dst_ref_g[name]
			var g := Transform3D()
			if name == "Root":
				g = ref
			elif name == "Body":
				# le bassin pilote tout le corps (rotation + translation mise à l'échelle)
				var s_ref: Transform3D = src_rest_g["pelvis"]
				var s_now: Transform3D = sg["pelvis"]
				var dq: Basis = s_now.basis.orthonormalized() * s_ref.basis.orthonormalized().inverse()
				g.basis = dq * ref.basis
				g.origin = ref.origin + (s_now.origin - s_ref.origin) * ratio
			else:
				var vp := _parent_name(name)
				var local_ref: Transform3D = dst_ref_g[vp].affine_inverse() * ref if vp != "" else ref
				g = (dg[vp] * local_ref) if vp != "" else ref
				if MAP.has(name):
					var sn: String = MAP[name]
					var dq2: Basis = sg[sn].basis.orthonormalized() * src_rest_g[sn].basis.orthonormalized().inverse()
					g.basis = dq2 * ref.basis
			dg[name] = g
		for name in rot_tracks:
			var p := _real_parent(name)
			var local: Transform3D = (dg[p].affine_inverse() * dg[name]) if p != "" else dg[name]
			out.rotation_track_insert_key(rot_tracks[name], t, local.basis.get_rotation_quaternion())
			if pos_tracks.has(name):
				out.position_track_insert_key(pos_tracks[name], t, local.origin)
	return out


func _freeze_last(src: Animation) -> Animation:
	var out := Animation.new()
	out.length = 1.0
	out.loop_mode = Animation.LOOP_LINEAR
	for tr in src.get_track_count():
		var nt := out.add_track(src.track_get_type(tr))
		out.track_set_path(nt, src.track_get_path(tr))
		var last := src.track_get_key_count(tr) - 1
		var v = src.track_get_key_value(tr, last)
		match src.track_get_type(tr):
			Animation.TYPE_ROTATION_3D:
				out.rotation_track_insert_key(nt, 0.0, v)
			Animation.TYPE_POSITION_3D:
				out.position_track_insert_key(nt, 0.0, v)
	return out
