extends Plugin

const POWERSTATION_PATH := "res://core/systems/performance/power_station.tres"
const MenuScene = preload(
	"res://plugins/panel-de-control/core/ui/power_status_menu.tscn"
)
const MenuIcon = preload("res://plugins/panel-de-control/assets/icon.svg")

var _powerstation: Variant
var _source_configured := false
var _ready_complete := false
var _menus: Array[WeakRef] = []


func configure_source(source: Variant) -> void:
	if _ready_complete:
		push_error("PowerStation source must be configured before the plugin is ready")
		return
	_powerstation = source
	_source_configured = true


func _ready() -> void:
	if not _source_configured:
		_powerstation = load(POWERSTATION_PATH)
	_ready_complete = true
	var quick_menu := _create_menu()
	add_to_quick_bar(quick_menu, MenuIcon)


func get_settings_menu() -> Control:
	if not _ready_complete:
		push_error("Settings menu requested before the plugin is ready")
		return null
	return _create_menu()


func unload() -> void:
	for menu_ref in _menus:
		var menu := menu_ref.get_ref() as Control
		if not is_instance_valid(menu):
			continue
		menu.call("shutdown")
		menu.queue_free()
	_menus.clear()
	_powerstation = null
	_source_configured = false
	_ready_complete = false


func _create_menu() -> Control:
	var menu := MenuScene.instantiate() as Control
	menu.call("configure_source", _powerstation)
	_menus.append(weakref(menu))
	return menu
