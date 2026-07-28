extends Plugin

const MenuScene = preload(
	"res://plugins/panel-de-control/core/ui/power_status_menu.tscn"
)
const MenuIcon = preload("res://plugins/panel-de-control/assets/icon.svg")
const PowerSnapshotSampler = preload(
	"res://plugins/panel-de-control/core/services/power_snapshot_sampler.gd"
)

var _sampler: Node
var _sampler_configured := false
var _ready_complete := false
var _menus: Array[WeakRef] = []


func configure_sampler(sampler: Node) -> void:
	if _ready_complete:
		push_error("Power sampler must be configured before the plugin is ready")
		return
	_sampler = sampler
	_sampler_configured = true


func _ready() -> void:
	_ensure_sampler()
	_ready_complete = true
	var quick_menu := _create_menu()
	add_to_quick_bar(quick_menu, MenuIcon)


func get_settings_menu() -> Control:
	_ensure_sampler()
	return _create_menu()


func unload() -> void:
	for menu_ref in _menus:
		var menu := menu_ref.get_ref() as Control
		if not is_instance_valid(menu):
			continue
		menu.call("shutdown")
		menu.queue_free()
	_menus.clear()
	if is_instance_valid(_sampler):
		_sampler.call("shutdown")
		_sampler.queue_free()
	_sampler = null
	_sampler_configured = false
	_ready_complete = false


func _create_menu() -> Control:
	var menu := MenuScene.instantiate() as Control
	menu.call("configure_sampler", _sampler)
	_menus.append(weakref(menu))
	return menu


func _ensure_sampler() -> void:
	if _sampler == null:
		_sampler = PowerSnapshotSampler.new()
	if _sampler.get_parent() == null:
		add_child(_sampler)
