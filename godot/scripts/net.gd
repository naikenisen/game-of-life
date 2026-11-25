class_name Net
extends Node
## Client TCP du pont Python (un message JSON par ligne). Reconnexion automatique.

signal got_init(d: Dictionary)
signal got_tick(d: Dictionary)
signal status_changed(text: String)

var host := "127.0.0.1"
var port := 7777
var peer := StreamPeerTCP.new()
var buf := PackedByteArray()
var connected := false
var retry := 0.0


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--port="):
			port = int(a.substr(7))
		elif a.begins_with("--host="):
			host = a.substr(7)
	_connect()


func _connect() -> void:
	peer = StreamPeerTCP.new()
	peer.connect_to_host(host, port)
	status_changed.emit("connexion à %s:%d…" % [host, port])


func send(obj: Dictionary) -> void:
	if connected:
		peer.put_data((JSON.stringify(obj) + "\n").to_utf8_buffer())


func _process(delta: float) -> void:
	peer.poll()
	var st := peer.get_status()
	if st == StreamPeerTCP.STATUS_CONNECTED:
		if not connected:
			connected = true
			peer.set_no_delay(true)
			status_changed.emit("connecté")
		var n := peer.get_available_bytes()
		if n > 0:
			var res := peer.get_partial_data(n)
			if res[0] == OK:
				buf.append_array(res[1])
		_parse()
	elif st == StreamPeerTCP.STATUS_ERROR or st == StreamPeerTCP.STATUS_NONE:
		if connected:
			connected = false
			status_changed.emit("déconnecté — lancez « python main.py --serve »")
		retry -= delta
		if retry <= 0:
			retry = 2.0
			_connect()


func _parse() -> void:
	var last := -1
	var handled := 0
	while true:
		var nl := buf.find(10, last + 1)
		if nl < 0:
			break
		var line := buf.slice(last + 1, nl).get_string_from_utf8()
		last = nl
		var d = JSON.parse_string(line)
		if typeof(d) != TYPE_DICTIONARY:
			continue
		if d.get("type") == "init":
			got_init.emit(d)
		elif d.get("type") == "tick":
			got_tick.emit(d)
		handled += 1
	if last >= 0:
		buf = buf.slice(last + 1)
