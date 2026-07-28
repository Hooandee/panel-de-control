extends GutTest

const MENU_PATH := "res://plugins/panel-de-control/core/ui/power_status_menu.tscn"
const PowerStationAdapter = preload(
	"res://plugins/panel-de-control/core/adapters/powerstation_adapter.gd"
)
const ObservedValue = preload(
	"res://plugins/panel-de-control/core/domain/observed_value.gd"
)


class ManualSampler extends Node:
	signal snapshot_updated(snapshot: RefCounted)

	var latest_snapshot: RefCounted
	var request_count := 0
	var poll_count := 0

	func _init(initial_snapshot: RefCounted) -> void:
		latest_snapshot = initial_snapshot

	func request_snapshot() -> bool:
		request_count += 1
		return true

	func get_latest_snapshot() -> RefCounted:
		return latest_snapshot

	func poll() -> void:
		poll_count += 1

	func publish(snapshot: RefCounted) -> void:
		latest_snapshot = snapshot
		snapshot_updated.emit(snapshot)


func test_known_shared_snapshot_is_rendered_and_refresh_only_requests_sampling() -> void:
	var fixture := _new_menu(_known_snapshot())
	var menu: Control = fixture["menu"]
	if menu == null:
		return
	var sampler: ManualSampler = fixture["sampler"]

	var section_label := menu.find_child("SectionLabel") as Label
	assert_not_null(section_label, "QuickBar API 2.0 requires a SectionLabel child")
	if section_label == null:
		return
	assert_eq(section_label.text, "Panel de Control")
	assert_eq(_label(menu, "PowerStationStatus").text, "PowerStation: Connected")
	assert_eq(_label(menu, "GpuValue").text, "GPU: AMD Radeon Graphics (1002:15bf)")
	assert_eq(_label(menu, "TdpValue").text, "Observed TDP: 18.0 W")
	assert_eq(_label(menu, "PowerProfileValue").text, "Power profile: balanced")
	assert_eq(sampler.request_count, 1)

	menu.refresh_now()

	assert_eq(sampler.request_count, 2)
	assert_eq(_label(menu, "TdpValue").text, "Observed TDP: 18.0 W")


func test_menu_drives_sampler_processing_from_its_live_scene_tree() -> void:
	var fixture := _new_menu(_known_snapshot())
	var menu: Control = fixture["menu"]
	if menu == null:
		return
	var sampler: ManualSampler = fixture["sampler"]

	menu.notification(Node.NOTIFICATION_PROCESS)

	assert_gt(
		sampler.poll_count,
		0,
		"OGUI can keep the plugin owner outside the live scene tree",
	)


func test_unavailable_snapshot_replaces_every_value_label() -> void:
	var fixture := _new_menu(_invalid_snapshot(
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable",
	))
	var menu: Control = fixture["menu"]
	if menu == null:
		return

	_assert_all_values(
		menu,
		"Unavailable (powerstation_unavailable_or_unreachable)",
	)


func test_unknown_snapshot_replaces_every_value_label() -> void:
	var fixture := _new_menu(_invalid_snapshot(
		ObservedValue.UNKNOWN,
		"integrated_gpu_not_found",
	))
	var menu: Control = fixture["menu"]
	if menu == null:
		return

	_assert_all_values(menu, "Unknown (integrated_gpu_not_found)")


func test_error_snapshot_replaces_every_value_label() -> void:
	var fixture := _new_menu(_invalid_snapshot(
		ObservedValue.ERROR,
		"busctl_response_invalid",
	))
	var menu: Control = fixture["menu"]
	if menu == null:
		return

	_assert_all_values(menu, "Error (busctl_response_invalid)")


func test_sampler_signal_clears_stale_known_values() -> void:
	var fixture := _new_menu(_known_snapshot())
	var menu: Control = fixture["menu"]
	if menu == null:
		return
	var sampler: ManualSampler = fixture["sampler"]
	assert_string_contains(_label(menu, "TdpValue").text, "18.0 W")

	sampler.publish(_invalid_snapshot(
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable",
	))

	_assert_all_values(
		menu,
		"Unavailable (powerstation_unavailable_or_unreachable)",
	)
	assert_eq(_label(menu, "TdpValue").text.find("18.0"), -1)
	assert_eq(_label(menu, "PowerProfileValue").text.find("balanced"), -1)


func test_menu_is_read_only_and_shutdown_disconnects_shared_sampler() -> void:
	var fixture := _new_menu(_known_snapshot())
	var menu: Control = fixture["menu"]
	if menu == null:
		return
	var sampler: ManualSampler = fixture["sampler"]
	var timer := menu.get_node("RefreshTimer") as Timer

	assert_false(timer.is_stopped())
	assert_eq(timer.wait_time, 1.0)
	assert_true(menu.find_children("*", "BaseButton", true, false).is_empty())
	assert_true(menu.find_children("*", "LineEdit", true, false).is_empty())
	assert_true(menu.find_children("*", "Range", true, false).is_empty())

	menu.shutdown()
	var requests_before_timeout := sampler.request_count
	timer.timeout.emit()
	sampler.publish(_invalid_snapshot(ObservedValue.ERROR, "late_snapshot"))

	assert_true(timer.is_stopped())
	assert_eq(sampler.request_count, requests_before_timeout)
	assert_eq(_label(menu, "PowerStationStatus").text, "PowerStation: Connected")


func _new_menu(snapshot: RefCounted) -> Dictionary:
	var scene := load(MENU_PATH) as PackedScene
	assert_not_null(scene, "the packaged power status scene must exist")
	if scene == null:
		return {"menu": null}
	var sampler := ManualSampler.new(snapshot)
	add_child_autofree(sampler)
	var menu := scene.instantiate() as Control
	menu.configure_sampler(sampler)
	add_child_autofree(menu)
	return {"menu": menu, "sampler": sampler}


func _label(menu: Control, node_name: String) -> Label:
	return menu.get_node("%" + node_name) as Label


func _assert_all_values(menu: Control, formatted_value: String) -> void:
	assert_eq(
		_label(menu, "PowerStationStatus").text,
		"PowerStation: %s" % formatted_value,
	)
	assert_eq(_label(menu, "GpuValue").text, "GPU: %s" % formatted_value)
	assert_eq(
		_label(menu, "TdpValue").text,
		"Observed TDP: %s" % formatted_value,
	)
	assert_eq(
		_label(menu, "PowerProfileValue").text,
		"Power profile: %s" % formatted_value,
	)


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


func _invalid_snapshot(state: String, reason: String) -> RefCounted:
	return PowerStationAdapter.new().invalid_snapshot(state, reason)
