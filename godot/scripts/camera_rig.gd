class_name CameraRig
extends Node3D
## Trois façons de visiter le monde :
##  - AERIAL : vue aérienne libre (déplacer, tourner, zoomer)
##  - VISITOR : à pied, à hauteur d'yeux, avec collisions (murs, eau)
##  - FOLLOW : caméra qui suit un habitant

enum Mode { AERIAL, VISITOR, FOLLOW }

var mode := Mode.AERIAL
var cam: Camera3D
var target := Vector3.ZERO       # point regardé (aérien / suivi)
var dist := 70.0
var yaw := 0.6
var pitch := -0.9
var look_yaw := 0.0               # visiteur
var look_pitch := 0.0
var vel := Vector3.ZERO
var follow_node: Node3D
var world: Node
var dragging_rot := false
var dragging_pan := false
var mouse_captured := false


func _ready() -> void:
	cam = Camera3D.new()
	cam.fov = 60
	cam.near = 0.1
	cam.far = 1500
	add_child(cam)
	cam.current = true


func set_mode(m: Mode) -> void:
	if m == Mode.VISITOR:
		var p := cam.global_position
		position = Vector3(p.x, 0, p.z) if mode != Mode.AERIAL else target
		look_yaw = yaw + PI
		look_pitch = 0.0
		_capture(true)
	else:
		if mode == Mode.VISITOR:
			target = position
		_capture(false)
	mode = m


func _capture(on: bool) -> void:
	mouse_captured = on
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if on else Input.MOUSE_MODE_VISIBLE


func focus_on(p: Vector3) -> void:
	target = p
	if mode == Mode.VISITOR:
		position = p + Vector3(3, 0, 3)


func follow(n: Node3D) -> void:
	follow_node = n
	if n:
		if mode == Mode.VISITOR:
			_capture(false)
		mode = Mode.FOLLOW
		dist = minf(dist, 13.0)
		pitch = -0.85


func _unhandled_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton:
		var mb := ev as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP and mb.pressed:
			dist = maxf(4.0, dist * 0.88)
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN and mb.pressed:
			dist = minf(320.0, dist * 1.14)
		elif mb.button_index == MOUSE_BUTTON_RIGHT:
			dragging_rot = mb.pressed
			if mode == Mode.VISITOR and mb.pressed:
				_capture(not mouse_captured)
		elif mb.button_index == MOUSE_BUTTON_MIDDLE:
			dragging_pan = mb.pressed
	elif ev is InputEventMouseMotion:
		var mm := ev as InputEventMouseMotion
		if mode == Mode.VISITOR and mouse_captured:
			look_yaw -= mm.relative.x * 0.0025
			look_pitch = clampf(look_pitch - mm.relative.y * 0.0025, -1.4, 1.4)
		elif dragging_rot:
			yaw -= mm.relative.x * 0.005
			pitch = clampf(pitch - mm.relative.y * 0.004, -1.45, -0.08)
		elif dragging_pan and mode == Mode.AERIAL:
			var right := Vector3(cos(yaw), 0, -sin(yaw))
			var fwd := Vector3(sin(yaw), 0, cos(yaw))
			target -= (right * mm.relative.x - fwd * mm.relative.y) * dist * 0.0015
	elif ev is InputEventKey and ev.pressed and ev.keycode == KEY_ESCAPE and mode == Mode.VISITOR:
		_capture(false)


func _process(delta: float) -> void:
	var input := Vector2(
		Input.get_axis("ui_left", "ui_right") + (float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))),
		Input.get_axis("ui_up", "ui_down") + (float(Input.is_physical_key_pressed(KEY_S)) - float(Input.is_physical_key_pressed(KEY_W))))
	var fast := Input.is_physical_key_pressed(KEY_SHIFT)
	match mode:
		Mode.AERIAL:
			if Input.is_physical_key_pressed(KEY_Q):
				yaw += delta * 1.5
			if Input.is_physical_key_pressed(KEY_E):
				yaw -= delta * 1.5
			var right := Vector3(cos(yaw), 0, -sin(yaw))
			var fwd := -Vector3(sin(yaw), 0, cos(yaw))
			target += (right * input.x - fwd * input.y) * delta * dist * (1.6 if fast else 0.8)
			_orbit(delta)
		Mode.FOLLOW:
			if follow_node and is_instance_valid(follow_node):
				target = target.lerp(follow_node.global_position + Vector3(0, 1.2, 0), minf(1.0, delta * 4.0))
			if Input.is_physical_key_pressed(KEY_Q):
				yaw += delta * 1.5
			if Input.is_physical_key_pressed(KEY_E):
				yaw -= delta * 1.5
			if input.length() > 0.1:
				mode = Mode.AERIAL
				follow_node = null
			_orbit(delta)
		Mode.VISITOR:
			var basis := Basis(Vector3.UP, look_yaw)
			var wish := basis * Vector3(input.x, 0, input.y)
			var spd := 9.0 if fast else 3.6
			vel = vel.lerp(wish * spd, minf(1.0, delta * 10.0))
			var np := position + vel * delta
			# collisions : on glisse le long des murs, on ne marche pas dans l'eau profonde
			if world.walkable(np.x, position.z):
				position.x = np.x
			if world.walkable(position.x, np.z):
				position.z = np.z
			var gy: float = world.floor_height(position.x, position.z)
			position.y = lerpf(position.y, maxf(gy, -0.2), minf(1.0, delta * 12.0))
			var bobbing := sin(Time.get_ticks_msec() * 0.011) * 0.04 * minf(vel.length() / 3.0, 1.0)
			cam.position = Vector3(0, 1.65 + bobbing, 0)
			cam.rotation = Vector3(look_pitch, look_yaw, 0)
			cam.fov = lerpf(cam.fov, 70.0, delta * 3.0)


func _orbit(delta: float) -> void:
	var w = world
	if w and w.has_method("floor_height"):
		var gy: float = w.floor_height(target.x, target.z)
		target.y = lerpf(target.y, gy + (1.2 if mode == Mode.FOLLOW else 0.0), minf(1.0, delta * 3.0))
	position = target
	var off := Vector3(0, 0, dist).rotated(Vector3.RIGHT, pitch).rotated(Vector3.UP, yaw)
	cam.position = off
	cam.look_at(target, Vector3.UP)
	cam.fov = lerpf(cam.fov, 55.0, delta * 3.0)
	# ne jamais passer sous le terrain
	var cg := cam.global_position
	if w and w.has_method("floor_height"):
		var floor_y: float = w.floor_height(cg.x, cg.z) + 1.0
		if cg.y < floor_y:
			cam.global_position = Vector3(cg.x, floor_y, cg.z)
			cam.look_at(target, Vector3.UP)
