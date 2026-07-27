extends GutTest

const PLUGIN_PATH := "res://plugins/panel-de-control/plugin.gd"
const FakePowerStation = preload("res://plugins/panel-de-control/tests/support/fake_powerstation.gd")


func test_ready_registers_quick_bar_and_settings_as_distinct_live_menus() -> void:
	var plugin := _new_plugin(FakePowerStation.new([_card()]))
	if plugin == null:
		return

	var quick_menu := plugin.registered_quick_bar as Control
	var settings_menu := plugin.get_settings_menu() as Control
	plugin.add_child(settings_menu)

	assert_not_null(quick_menu)
	assert_not_null(settings_menu)
	assert_ne(quick_menu, settings_menu)
	assert_false((quick_menu.get_node("RefreshTimer") as Timer).is_stopped())
	assert_eq((quick_menu.get_node("RefreshTimer") as Timer).wait_time, 1.0)
	assert_false((settings_menu.get_node("RefreshTimer") as Timer).is_stopped())


func test_registered_menu_refreshes_when_timer_expires() -> void:
	var source = FakePowerStation.new([_card()])
	var plugin := _new_plugin(source)
	if plugin == null:
		return
	var quick_menu := plugin.registered_quick_bar as Control
	var timer := quick_menu.get_node("RefreshTimer") as Timer
	var tdp_label := quick_menu.get_node("%TdpValue") as Label
	assert_eq(tdp_label.text, "Observed TDP: 18.0 W")

	source.running = false
	timer.timeout.emit()

	assert_eq(
		tdp_label.text,
		"Observed TDP: Unavailable (powerstation_not_running)"
	)


func test_unload_stops_all_menus_frees_them_and_releases_source() -> void:
	var source: Variant = FakePowerStation.new([_card()])
	var source_ref: WeakRef = weakref(source)
	var plugin := _new_plugin(source)
	if plugin == null:
		return
	source = null

	var quick_menu := plugin.registered_quick_bar as Control
	var settings_menu := plugin.get_settings_menu() as Control
	plugin.add_child(settings_menu)
	var quick_ref: WeakRef = weakref(quick_menu)
	var settings_ref: WeakRef = weakref(settings_menu)
	var quick_timer := quick_menu.get_node("RefreshTimer") as Timer
	var settings_timer := settings_menu.get_node("RefreshTimer") as Timer

	plugin.unload()

	assert_true(quick_timer.is_stopped())
	assert_true(settings_timer.is_stopped())
	await get_tree().process_frame
	assert_null(quick_ref.get_ref())
	assert_null(settings_ref.get_ref())
	assert_null(source_ref.get_ref())


func _new_plugin(source: Variant) -> Node:
	var plugin_script := load(PLUGIN_PATH) as GDScript
	assert_not_null(plugin_script, "the packaged plugin entry point must exist")
	if plugin_script == null:
		return null
	var plugin := plugin_script.new() as Node
	plugin.configure_source(source)
	add_child_autofree(plugin)
	return plugin


func _card() -> Dictionary:
	return {
		"dbus_path": "/org/shadowblip/Performance/GPU/card1",
		"class": "integrated",
		"name": "AMD Radeon Graphics",
		"device": "1002:15bf",
		"supports_tdp": true,
		"tdp": 18.0,
		"power_profile": "balanced",
	}
