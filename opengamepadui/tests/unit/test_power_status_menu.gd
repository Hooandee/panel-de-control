extends GutTest

const MENU_PATH := "res://plugins/panel-de-control/core/ui/power_status_menu.tscn"
const FakePowerStation = preload("res://plugins/panel-de-control/tests/support/fake_powerstation.gd")


class InvalidGpu extends RefCounted:
	func get_cards() -> Variant:
		return {}


class InvalidPowerStation extends RefCounted:
	func is_running() -> bool:
		return true

	func get_gpu() -> Variant:
		return InvalidGpu.new()


func test_known_snapshot_is_rendered_as_observed_values() -> void:
	var source = FakePowerStation.new([_card()])
	var menu := _new_menu(source)
	if menu == null:
		return

	var section_label := menu.find_child("SectionLabel") as Label
	assert_not_null(section_label, "QuickBar API 2.0 requires a SectionLabel child")
	if section_label == null:
		return
	assert_eq(section_label.text, "Panel de Control")
	assert_eq(_label(menu, "PowerStationStatus").text, "PowerStation: Connected")
	assert_eq(_label(menu, "GpuValue").text, "GPU: AMD Radeon Graphics (1002:15bf)")
	assert_eq(_label(menu, "TdpValue").text, "Observed TDP: 18.0 W")
	assert_eq(_label(menu, "PowerProfileValue").text, "Power profile: balanced")
	assert_eq(source.write_attempts(), 0)


func test_unavailable_snapshot_replaces_every_value_label() -> void:
	var menu := _new_menu(null)
	if menu == null:
		return

	assert_eq(
		_label(menu, "PowerStationStatus").text,
		"PowerStation: Unavailable (powerstation_unavailable)"
	)
	assert_eq(_label(menu, "GpuValue").text, "GPU: Unavailable (powerstation_unavailable)")
	assert_eq(
		_label(menu, "TdpValue").text,
		"Observed TDP: Unavailable (powerstation_unavailable)"
	)
	assert_eq(
		_label(menu, "PowerProfileValue").text,
		"Power profile: Unavailable (powerstation_unavailable)"
	)


func test_unknown_snapshot_replaces_every_value_label() -> void:
	var source = FakePowerStation.new([_card({"class": "discrete"})])
	var menu := _new_menu(source)
	if menu == null:
		return

	assert_eq(
		_label(menu, "PowerStationStatus").text,
		"PowerStation: Unknown (integrated_gpu_not_found)"
	)
	assert_eq(_label(menu, "GpuValue").text, "GPU: Unknown (integrated_gpu_not_found)")
	assert_eq(
		_label(menu, "TdpValue").text,
		"Observed TDP: Unknown (integrated_gpu_not_found)"
	)
	assert_eq(
		_label(menu, "PowerProfileValue").text,
		"Power profile: Unknown (integrated_gpu_not_found)"
	)


func test_error_snapshot_replaces_every_value_label() -> void:
	var menu := _new_menu(InvalidPowerStation.new())
	if menu == null:
		return

	assert_eq(
		_label(menu, "PowerStationStatus").text,
		"PowerStation: Error (gpu_cards_invalid)"
	)
	assert_eq(_label(menu, "GpuValue").text, "GPU: Error (gpu_cards_invalid)")
	assert_eq(_label(menu, "TdpValue").text, "Observed TDP: Error (gpu_cards_invalid)")
	assert_eq(
		_label(menu, "PowerProfileValue").text,
		"Power profile: Error (gpu_cards_invalid)"
	)


func test_refresh_clears_known_values_when_source_becomes_unavailable() -> void:
	var source = FakePowerStation.new([_card()])
	var menu := _new_menu(source)
	if menu == null:
		return
	assert_string_contains(_label(menu, "TdpValue").text, "18.0 W")

	source.running = false
	menu.refresh_now()

	assert_eq(
		_label(menu, "PowerStationStatus").text,
		"PowerStation: Unavailable (powerstation_not_running)"
	)
	assert_eq(_label(menu, "GpuValue").text, "GPU: Unavailable (powerstation_not_running)")
	assert_eq(
		_label(menu, "TdpValue").text,
		"Observed TDP: Unavailable (powerstation_not_running)"
	)
	assert_eq(
		_label(menu, "PowerProfileValue").text,
		"Power profile: Unavailable (powerstation_not_running)"
	)
	assert_eq(_label(menu, "TdpValue").text.find("18.0"), -1)
	assert_eq(_label(menu, "PowerProfileValue").text.find("balanced"), -1)
	assert_eq(source.write_attempts(), 0)


func test_menu_is_read_only_and_shutdown_stops_refresh_and_releases_source() -> void:
	var source: Variant = FakePowerStation.new([_card()])
	var source_ref: WeakRef = weakref(source)
	var menu := _new_menu(source)
	if menu == null:
		return
	var timer := menu.get_node("RefreshTimer") as Timer

	assert_false(timer.is_stopped())
	assert_eq(timer.wait_time, 1.0)
	assert_true(menu.find_children("*", "BaseButton", true, false).is_empty())
	assert_true(menu.find_children("*", "LineEdit", true, false).is_empty())
	assert_true(menu.find_children("*", "Range", true, false).is_empty())

	source = null
	menu.shutdown()

	assert_true(timer.is_stopped())
	assert_null(source_ref.get_ref())


func _new_menu(source: Variant) -> Control:
	var scene := load(MENU_PATH) as PackedScene
	assert_not_null(scene, "the packaged power status scene must exist")
	if scene == null:
		return null
	var menu := scene.instantiate() as Control
	menu.configure_source(source)
	add_child_autofree(menu)
	return menu


func _label(menu: Control, node_name: String) -> Label:
	return menu.get_node("%" + node_name) as Label


func _card(overrides: Dictionary = {}) -> Dictionary:
	var data := {
		"dbus_path": "/org/shadowblip/Performance/GPU/card1",
		"class": "integrated",
		"name": "AMD Radeon Graphics",
		"device": "1002:15bf",
		"supports_tdp": true,
		"tdp": 18.0,
		"power_profile": "balanced",
	}
	data.merge(overrides, true)
	return data
