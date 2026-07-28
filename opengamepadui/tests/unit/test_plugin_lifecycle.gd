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
	var poll_count := 0
	var shutdown_called := false

	func _init(initial_snapshot: RefCounted) -> void:
		latest_snapshot = initial_snapshot

	func request_snapshot() -> bool:
		request_count += 1
		return true

	func poll() -> void:
		poll_count += 1

	func get_latest_snapshot() -> RefCounted:
		return latest_snapshot

	func publish(snapshot: RefCounted) -> void:
		latest_snapshot = snapshot
		snapshot_updated.emit(snapshot)

	func shutdown() -> void:
		shutdown_called = true


func test_entering_tree_does_not_register_an_unsafe_quick_bar_menu() -> void:
	var sampler := FakeSampler.new(_known_snapshot())
	var plugin_script := load(PLUGIN_PATH) as GDScript
	assert_not_null(plugin_script, "the packaged plugin entry point must exist")
	if plugin_script == null:
		return
	var plugin := plugin_script.new() as Node
	plugin.configure_sampler(sampler)
	add_child_autofree(plugin)

	assert_null(
		plugin.registered_quick_bar,
		"OGUI 0.46 cannot safely host this plugin in Quick Bar",
	)
	plugin.unload()
	await get_tree().process_frame


func test_live_settings_menus_drive_one_sampler_while_plugin_stays_detached() -> void:
	var sampler: Variant = FakeSampler.new(_known_snapshot())
	var fixture := _new_detached_plugin(sampler as Node)
	var plugin: Node = fixture["plugin"]
	if plugin == null:
		return
	var detached_manager: Node = fixture["manager"]
	var host := Control.new()
	add_child_autofree(host)

	var first_menu := plugin.get_settings_menu() as Control
	var second_menu := plugin.get_settings_menu() as Control
	host.add_child(first_menu)
	host.add_child(second_menu)

	assert_false(plugin.is_inside_tree())
	assert_null(plugin.registered_quick_bar)
	assert_eq(first_menu.get_parent(), host)
	assert_eq(second_menu.get_parent(), host)
	assert_eq(sampler.get_parent(), plugin)
	assert_eq(sampler.request_count, 2)
	assert_eq(_label(first_menu, "TdpValue").text, "Observed TDP: 18.0 W")
	assert_eq(_label(second_menu, "TdpValue").text, "Observed TDP: 18.0 W")
	first_menu.notification(Node.NOTIFICATION_PROCESS)
	assert_gt(sampler.poll_count, 0)
	sampler.publish(PowerStationAdapter.new().invalid_snapshot(
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable",
	))

	assert_eq(
		_label(first_menu, "TdpValue").text,
		"Observed TDP: Unavailable (powerstation_unavailable_or_unreachable)",
	)
	assert_eq(
		_label(second_menu, "TdpValue").text,
		"Observed TDP: Unavailable (powerstation_unavailable_or_unreachable)",
	)
	var sampler_ref: WeakRef = weakref(sampler)
	var first_ref: WeakRef = weakref(first_menu)
	var second_ref: WeakRef = weakref(second_menu)
	var first_timer := first_menu.get_node("RefreshTimer") as Timer
	var second_timer := second_menu.get_node("RefreshTimer") as Timer

	plugin.unload()

	assert_true(sampler.shutdown_called)
	assert_true(first_timer.is_stopped())
	assert_true(second_timer.is_stopped())
	sampler = null
	await get_tree().process_frame
	assert_null(first_ref.get_ref())
	assert_null(second_ref.get_ref())
	assert_null(sampler_ref.get_ref())
	detached_manager.free()


func test_sampler_configuration_cannot_replace_an_existing_instance() -> void:
	var first_sampler := FakeSampler.new(_known_snapshot())
	var second_sampler := FakeSampler.new(
		PowerStationAdapter.new().snapshot_from_properties(
			{
				"dbus_path": "/org/shadowblip/Performance/GPU/card1",
				"class": "integrated",
				"name": "Different GPU",
				"device": "ffff:ffff",
			},
			{"tdp": 22.0, "power_profile": "balanced"},
		),
	)
	var plugin_script := load(PLUGIN_PATH) as GDScript
	assert_not_null(plugin_script, "the packaged plugin entry point must exist")
	if plugin_script == null:
		return
	var plugin := plugin_script.new() as Node
	var manager := Node.new()
	manager.add_child(plugin)
	var existing_owner := Node.new()
	var parented_sampler := FakeSampler.new(_known_snapshot())
	existing_owner.add_child(parented_sampler)

	assert_false(plugin.configure_sampler(null))
	assert_false(plugin.configure_sampler(parented_sampler))
	assert_true(plugin.configure_sampler(first_sampler))
	assert_false(plugin.configure_sampler(second_sampler))
	second_sampler.free()
	existing_owner.free()

	var host := Control.new()
	add_child_autofree(host)
	var menu := plugin.get_settings_menu() as Control
	host.add_child(menu)
	assert_eq(_label(menu, "TdpValue").text, "Observed TDP: 18.0 W")
	plugin.unload()
	manager.free()


func _new_detached_plugin(sampler: Node) -> Dictionary:
	var plugin_script := load(PLUGIN_PATH) as GDScript
	assert_not_null(plugin_script, "the packaged plugin entry point must exist")
	if plugin_script == null:
		return {"plugin": null}
	var plugin := plugin_script.new() as Node
	assert_true(plugin.configure_sampler(sampler))
	var manager := Node.new()
	manager.add_child(plugin)
	return {"plugin": plugin, "manager": manager}


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
