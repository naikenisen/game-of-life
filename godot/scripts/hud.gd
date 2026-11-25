class_name Hud
extends CanvasLayer
## Interface : barre du haut, fiche de l'habitant (façon Sims), journal,
## minicarte, noms et bulles de dialogue au-dessus des têtes.

const ACT_FR := {
	"idle": "se repose un instant", "walk": "marche", "chop": "coupe du bois", "mine": "mine la roche",
	"dig": "creuse", "pick": "cueille", "harvest": "récolte le blé", "plant": "plante", "farm": "laboure",
	"build": "construit", "craft": "fabrique", "fight": "se bat", "eat": "mange", "eat_seated": "mange à table",
	"sit": "est assis(e)", "read": "lit", "sleep": "dort", "sleep_bed": "dort dans son lit",
	"sit_ground": "s'est assis(e) par terre", "dance": "danse", "celebrate": "fait la fête", "cry": "pleure",
	"idle_look": "observe les alentours", "talk": "discute", "give": "donne quelque chose", "dress": "se change",
	"drink": "boit au puits", "fish": "pêche",
}
const NEEDS := [["hu", "Faim"], ["en", "Énergie"], ["so", "Social"], ["fu", "Loisirs"]]

var main: Node
var top_label: RichTextLabel
var status_label: Label
var panel: PanelContainer
var panel_body: RichTextLabel
var panel_title: Label
var need_bars := {}
var events_box: RichTextLabel
var overlay: Control
var minimap: TextureRect
var minimap_img: Image
var help: PanelContainer
var speed_buttons := []
var font: Font


func _ready() -> void:
	layer = 5
	font = ThemeDB.fallback_font
	overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.draw.connect(_draw_overlay)
	add_child(overlay)
	_build_top()
	_build_panel()
	_build_events()
	_build_minimap()
	_build_help()


func _style(bg := Color(0.08, 0.09, 0.12, 0.82), radius := 10) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = bg
	s.set_corner_radius_all(radius)
	s.content_margin_left = 12
	s.content_margin_right = 12
	s.content_margin_top = 8
	s.content_margin_bottom = 8
	return s


func _build_top() -> void:
	var bar := PanelContainer.new()
	bar.add_theme_stylebox_override("panel", _style())
	bar.position = Vector2(12, 10)
	add_child(bar)
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 14)
	bar.add_child(hb)
	top_label = RichTextLabel.new()
	top_label.bbcode_enabled = true
	top_label.fit_content = true
	top_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	top_label.custom_minimum_size = Vector2(520, 0)
	top_label.scroll_active = false
	hb.add_child(top_label)
	for s in [["⏸", 0], ["▶", 2], ["▶▶", 6], ["▶▶▶", 20]]:
		var b := Button.new()
		b.text = s[0]
		b.custom_minimum_size = Vector2(48, 0)
		b.focus_mode = Control.FOCUS_NONE
		b.pressed.connect(func(): main.set_speed(s[1]))
		hb.add_child(b)
		speed_buttons.append(b)
	for s in [["Vue aérienne", "aerial"], ["Visiteur", "visitor"], ["Toits", "roofs"]]:
		var b := Button.new()
		b.text = s[0]
		b.focus_mode = Control.FOCUS_NONE
		b.pressed.connect(func(): main.ui_action(s[1]))
		hb.add_child(b)
	status_label = Label.new()
	status_label.position = Vector2(14, 58)
	status_label.add_theme_color_override("font_color", Color(1, 0.85, 0.5))
	add_child(status_label)


func _build_panel() -> void:
	panel = PanelContainer.new()
	panel.add_theme_stylebox_override("panel", _style(Color(0.07, 0.08, 0.11, 0.88), 14))
	panel.custom_minimum_size = Vector2(390, 0)
	panel.visible = false
	add_child(panel)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 6)
	panel.add_child(vb)
	var head := HBoxContainer.new()
	vb.add_child(head)
	panel_title = Label.new()
	panel_title.add_theme_font_size_override("font_size", 22)
	panel_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(panel_title)
	for s in [["Suivre", "follow"], ["Aller voir", "goto"], ["✕", "close"]]:
		var b := Button.new()
		b.text = s[0]
		b.focus_mode = Control.FOCUS_NONE
		b.pressed.connect(func(): main.ui_action(s[1]))
		head.add_child(b)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 10)
	vb.add_child(grid)
	for n in NEEDS + [["hp", "Santé"], ["mood", "Humeur"]]:
		var l := Label.new()
		l.text = n[1]
		l.custom_minimum_size = Vector2(70, 0)
		grid.add_child(l)
		var bar := ProgressBar.new()
		bar.max_value = 100
		bar.show_percentage = false
		bar.custom_minimum_size = Vector2(280, 16)
		grid.add_child(bar)
		need_bars[n[0]] = bar
	panel_body = RichTextLabel.new()
	panel_body.bbcode_enabled = true
	panel_body.fit_content = true
	panel_body.custom_minimum_size = Vector2(366, 0)
	panel_body.scroll_active = false
	vb.add_child(panel_body)


func _build_events() -> void:
	events_box = RichTextLabel.new()
	events_box.bbcode_enabled = true
	events_box.scroll_following = true
	events_box.add_theme_stylebox_override("normal", _style(Color(0.05, 0.06, 0.08, 0.55), 10))
	events_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	events_box.add_theme_font_size_override("normal_font_size", 13)
	add_child(events_box)


func _build_minimap() -> void:
	minimap = TextureRect.new()
	minimap.stretch_mode = TextureRect.STRETCH_SCALE
	minimap.gui_input.connect(_minimap_input)
	add_child(minimap)


func _build_help() -> void:
	help = PanelContainer.new()
	help.add_theme_stylebox_override("panel", _style(Color(0.05, 0.06, 0.08, 0.92), 14))
	help.visible = false
	var l := Label.new()
	l.text = """COMMANDES
Vue aérienne : ZQSD / flèches pour se déplacer, A/E (ou Q/E) pour tourner,
    molette pour zoomer, clic droit + glisser pour pivoter, clic molette pour glisser.
V : passer en mode visiteur (à pied) — souris pour regarder, ZQSD pour marcher,
    Maj pour courir, clic droit pour libérer/capturer la souris.
Clic gauche sur un habitant : sa fiche (besoins, pensées, plan, inventaire).
F : suivre l'habitant sélectionné     Tab : habitant suivant
R : toits (auto / visibles / cachés)   Espace : pause   1-4 : vitesse
H : cette aide     Échap : désélectionner / libérer la souris"""
	help.add_child(l)
	add_child(help)


var _last_vs := Vector2.ZERO
var _last_panel_w := 0.0


func _process(_delta: float) -> void:
	var vs := get_viewport().get_visible_rect().size
	# on ne repositionne l'interface que si la fenêtre change (éviter des re-mises en page coûteuses)
	if vs != _last_vs or panel.size.x != _last_panel_w:
		_last_vs = vs
		_last_panel_w = panel.size.x
		panel.position = Vector2(vs.x - panel.size.x - 12, 70)
		events_box.position = Vector2(12, vs.y - 230)
		events_box.size = Vector2(560, 218)
		help.position = (vs - help.size) / 2
		if minimap.texture:
			var ms := Vector2(260, 260.0 * minimap_img.get_height() / minimap_img.get_width())
			minimap.size = ms
			minimap.position = Vector2(vs.x - ms.x - 12, vs.y - ms.y - 12)
	overlay.queue_redraw()


# ---------------------------------------------------------------- mises à jour
func set_status(t: String) -> void:
	status_label.text = t


func update_top(d: Dictionary, people_alive: int, mode_name: String) -> void:
	var llm = d.get("llm")
	var cost := ""
	if llm != null:
		cost = "   [color=#9fb0c8]LLM %d appels · %.3f $[/color]" % [llm.get("calls", 0), llm.get("cost", 0.0)]
	var icon := "🌙" if d.get("night", false) else "☀"
	top_label.text = "[b]%s Jour %d — %s[/b]   [color=#c8d0dc]%d habitants · %s · %s · %d i/s[/color]%s" % [
		icon, d.get("day", 1), d.get("hour", ""), people_alive, mode_name,
		"en pause" if d.get("paused", false) else "%d ticks/s" % d.get("tps", 2), Engine.get_frames_per_second(), cost]


func add_events(list: Array) -> void:
	for e in list:
		var col := "#dfe6ee"
		if "☠" in e or "⚔" in e:
			col = "#ff8a80"
		elif "👶" in e:
			col = "#a5d6a7"
		elif "«" in e:
			col = "#b3c7e6"
		events_box.append_text("[color=%s]%s[/color]\n" % [col, e])
	if events_box.get_paragraph_count() > 60:
		events_box.remove_paragraph(0)


func show_person(p: Person) -> void:
	panel.visible = p != null
	if p == null:
		return
	var d := p.data
	panel_title.text = p.pname
	panel_title.add_theme_color_override("font_color", p.color.lightened(0.3))
	for k in need_bars:
		var v: float = d.get(k, 0)
		if k == "hp":
			v = v * 5.0
		var bar: ProgressBar = need_bars[k]
		bar.value = v
		var c := Color(0.85, 0.25, 0.2).lerp(Color(0.3, 0.85, 0.35), clampf(v / 100.0, 0, 1))
		var sb := StyleBoxFlat.new()
		sb.bg_color = c
		sb.set_corner_radius_all(4)
		bar.add_theme_stylebox_override("fill", sb)
	var act: String = d.get("act", "idle")
	var lines := []
	if not d.get("alive", true):
		lines.append("[color=#ff8a80][b]Décédé(e)[/b] — %s[/color]" % d.get("death", ""))
	else:
		lines.append("[b]%s[/b] %s" % [p.pname, ACT_FR.get(act, act)] + ("  [color=#90caf9](réfléchit…)[/color]" if d.get("think", false) else ""))
	if d.get("th", "") != "":
		lines.append("[i][color=#cfd8dc]« %s »[/color][/i]" % d["th"])
	if d.get("say", "") != "":
		lines.append("[color=#fff59d]💬 %s[/color]" % d["say"])
	var plan: Array = d.get("plan", [])
	if plan.size() > 0:
		lines.append("[color=#9fb0c8]Plan :[/color] " + " → ".join(plan) + (" [color=#80cbc4](routine)[/color]" if d.get("routine", false) else ""))
	var inv: Dictionary = d.get("inv", {})
	if inv.size() > 0:
		var parts := []
		for k in inv:
			parts.append("%s %d" % [k, inv[k]])
		lines.append("[color=#9fb0c8]Sac :[/color] " + ", ".join(parts))
	if d.get("notes", "") != "":
		lines.append("[color=#9fb0c8]Notes :[/color] " + d["notes"])
	var mem: Array = d.get("mem", [])
	if mem.size() > 0:
		lines.append("[color=#9fb0c8]Souvenirs :[/color]")
		for m in mem.slice(-4):
			lines.append("  · " + m)
	panel_body.text = "\n".join(lines)


func update_minimap(img: Image) -> void:
	minimap_img = img
	if minimap.texture == null:
		minimap.texture = ImageTexture.create_from_image(img)
		_last_vs = Vector2.ZERO
	else:
		(minimap.texture as ImageTexture).update(img)


func _minimap_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton and ev.pressed and ev.button_index == MOUSE_BUTTON_LEFT:
		var uv: Vector2 = ev.position / minimap.size
		main.jump_to_uv(uv)


func toggle_help() -> void:
	help.visible = not help.visible


# ---------------------------------------------------------------- noms et bulles
func _draw_overlay() -> void:
	if main == null or main.cam_rig == null:
		return
	var cam: Camera3D = main.cam_rig.cam
	var vs := get_viewport().get_visible_rect().size
	for p in main.persons.values():
		if not p.visible or not p.alive:
			continue
		var hp: Vector3 = p.head_position()
		var dist := cam.global_position.distance_to(hp)
		if dist > 75 or cam.is_position_behind(hp):
			continue
		var sp := cam.unproject_position(hp)
		if sp.x < -50 or sp.y < -50 or sp.x > vs.x + 50 or sp.y > vs.y + 50:
			continue
		var alpha := clampf(1.4 - dist / 60.0, 0.25, 1.0)
		var fs := int(clampf(18 - dist * 0.12, 11, 17))
		var name_w := font.get_string_size(p.pname, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
		var sel: bool = main.selected == p
		overlay.draw_string_outline(font, sp + Vector2(-name_w / 2, 0), p.pname, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, 4, Color(0, 0, 0, 0.7 * alpha))
		overlay.draw_string(font, sp + Vector2(-name_w / 2, 0), p.pname, HORIZONTAL_ALIGNMENT_LEFT, -1, fs,
			(Color(1, 1, 0.6) if sel else p.color.lightened(0.45)) * Color(1, 1, 1, alpha))
		if p.data.get("think", false):
			overlay.draw_string(font, sp + Vector2(name_w / 2 + 4, 0), "💭", HORIZONTAL_ALIGNMENT_LEFT, -1, fs)
		var say: String = p.data.get("say", "")
		if say != "" and dist < 55:
			_bubble(sp + Vector2(0, -fs - 6), say, alpha)


func _bubble(anchor: Vector2, text: String, alpha: float) -> void:
	var fs := 14
	var maxw := 260.0
	var words := text.split(" ")
	var lines := []
	var cur := ""
	for wd in words:
		var trial := (cur + " " + wd).strip_edges()
		if font.get_string_size(trial, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x > maxw and cur != "":
			lines.append(cur)
			cur = wd
		else:
			cur = trial
	if cur != "":
		lines.append(cur)
	lines = lines.slice(0, 4)
	var lh := fs + 4
	var bw := 0.0
	for l in lines:
		bw = maxf(bw, font.get_string_size(l, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x)
	var rect := Rect2(anchor + Vector2(-bw / 2 - 10, -lines.size() * lh - 12), Vector2(bw + 20, lines.size() * lh + 10))
	var bg := Color(1, 1, 0.97, 0.93 * alpha)
	overlay.draw_rect(rect, bg)
	overlay.draw_colored_polygon(PackedVector2Array([anchor + Vector2(-7, -2), anchor + Vector2(7, -2), anchor + Vector2(0, 8)]), bg)
	var y := rect.position.y + lh
	for l in lines:
		overlay.draw_string(font, Vector2(rect.position.x + 10, y), l, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(0.1, 0.1, 0.12, alpha))
		y += lh
