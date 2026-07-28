extends GutTest

const PLUGIN_PATH := "res://plugins/panel-de-control/plugin.gd"
const PowerStationAdapter = preload(
	"res://plugins/panel-de-control/core/adapters/powerstation_adapter.gd"
)
const ObservedValue = preload(
	"res://plugins/panel-de-control/core/domain/observed_value.gd"
)


class FakeSampler extends Node:
	signal snapshot_updated(snapshot: RefCounted)

	var latest_snapshot: RefCounted
	var request_count := 0
	var shutdown_called := false

	func _init(initial_snapshot: RefCounted) -> void:
		latest_snapshot = initial_snapshot

	func request_snapshot() -> bool:
		request_count += 1
		return true

	func poll() -> void:
		pass

	func get_latest_snapshot() -> RefCounted:
		return latest_snapshot

	func publish(snapshot: RefCounted) -> void:
		latest_snapshot = snapshot
		snapshot_updated.emit(snapshot)

	func shutdown() -> void:
		shutdown_called = true


func test_settings_menu_is_available_before_plugin_enters_scene_tree() -> void:
	var sampler := FakeSampler.new(_known_snapshot())
	var plugin_script := load(PLUGIN_PATH) as GDScript
	assert_not_null(plugin_script, "the packaged plugin entry point must exist")
	if plugin_script == null:
		return
	var plugin := plugin_script.new() as Node
	plugin.configure_sampler(sampler)

	var settings_menu := plugin.get_settings_menu() as Control

	assert_not_null(
		settings_menu,
		"OGUI requests settings while the PluginManager is still outside the tree",
	)
	if settings_menu != null:
		settings_menu.free()
	plugin.free()


func test_plugin_owns_one_sampler_shared_by_quick_bar_and_settings() -> void:
	var sampler := FakeSampler.new(_known_snapshot())
	var plugin := _new_plugin(sampler)
	if plugin == null:
		return

	var quick_menu := plugin.registered_quick_bar as Control
	var settings_menu := plugin.get_settings_menu() as Control
	plugin.add_child(settings_menu)

	assert_not_null(quick_menu)
	assert_not_null(settings_menu)
	assert_ne(quick_menu, settings_menu)
	assert_eq(sampler.get_parent(), plugin)
	assert_eq(sampler.request_count, 2)
	assert_eq(_label(quick_menu, "TdpValue").text, "Observed TDP: 18.0 W")
	assert_eq(_label(settings_menu, "TdpValue").text, "Observed TDP: 18.0 W")
	assert_false((quick_menu.get_node("RefreshTimer") as Timer).is_stopped())
	assert_false((settings_menu.get_node("RefreshTimer") as Timer).is_stopped())

	(quick_menu.get_node("RefreshTimer") as Timer).timeout.emit()
	(settings_menu.get_node("RefreshTimer") as Timer).timeout.emit()

	assert_eq(sampler.request_count, 4)


func test_one_sampler_signal_refreshes_every_live_menu() -> void:
	var sampler := FakeSampler.new(_known_snapshot())
	var plugin := _new_plugin(sampler)
	if plugin == null:
		return
	var quick_menu := plugin.registered_quick_bar as Control
	var settings_menu := plugin.get_settings_menu() as Control
	plugin.add_child(settings_menu)

	sampler.publish(PowerStationAdapter.new().invalid_snapshot(
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable",
	))

	assert_eq(
		_label(quick_menu, "TdpValue").text,
		"Observed TDP: Unavailable (powerstation_unavailable_or_unreachable)",
	)
	assert_eq(
		_label(settings_menu, "TdpValue").text,
		"Observed TDP: Unavailable (powerstation_unavailable_or_unreachable)",
	)


func test_unload_stops_menus_shuts_down_sampler_and_releases_everything() -> void:
	var sampler: Variant = FakeSampler.new(_known_snapshot())
	var sampler_ref: WeakRef = weakref(sampler)
	var plugin: Node = _new_plugin(sampler as Node)
	if plugin == null:
		return

	var quick_menu := plugin.registered_quick_bar as Control
	var settings_menu := plugin.get_settings_menu() as Control
	plugin.add_child(settings_menu)
	var quick_ref: WeakRef = weakref(quick_menu)
	var settings_ref: WeakRef = weakref(settings_menu)
	var quick_timer := quick_menu.get_node("RefreshTimer") as Timer
	var settings_timer := settings_menu.get_node("RefreshTimer") as Timer

	plugin.unload()

	assert_true(sampler.shutdown_called)
	assert_true(quick_timer.is_stopped())
	assert_true(settings_timer.is_stopped())
	sampler = null
	await get_tree().process_frame
	assert_null(quick_ref.get_ref())
	assert_null(settings_ref.get_ref())
	assert_null(sampler_ref.get_ref())


func _new_plugin(sampler: Node) -> Node:
	var plugin_script := load(PLUGIN_PATH) as GDScript
	assert_not_null(plugin_script, "the packaged plugin entry point must exist")
	if plugin_script == null:
		return null
	var plugin := plugin_script.new() as Node
	plugin.configure_sampler(sampler)
	add_child_autofree(plugin)
	return plugin


func _label(menu: Control, node_name: String) -> Label:
	return menu.get_node("%" + node_name) as Label


func _known_snapshot() -> RefCounted:
	return PowerStationAdapter.new().snapshot_from_properties(
		{
			"dbus_path": "/org/shadowblip/Performance/GPU/card1",
			"class": "integrated",
			"name": "AMD Radeon Graphics",
			"device": "1002:15bf",
		},
		{"tdp": 18.0, "power_profile": "balanced"},
	)
