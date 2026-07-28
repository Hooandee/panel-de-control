extends Plugin

const MenuScene = preload(
	"res://plugins/panel-de-control/core/ui/power_status_menu.tscn"
)
const PowerSnapshotSampler = preload(
	"res://plugins/panel-de-control/core/services/power_snapshot_sampler.gd"
)

var _sampler: Node
var _menus: Array[WeakRef] = []


func configure_sampler(sampler: Node) -> bool:
	if sampler == null or sampler.get_parent() != null or _sampler != null:
		return false
	_sampler = sampler
	return true


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
