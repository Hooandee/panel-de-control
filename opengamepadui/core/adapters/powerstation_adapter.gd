extends RefCounted

const ObservedValue = preload("res://plugins/panel-de-control/core/domain/observed_value.gd")
const PowerSnapshot = preload("res://plugins/panel-de-control/core/domain/power_snapshot.gd")

var _clock: Callable
var _generation := 0


func _init(clock: Callable = Callable()) -> void:
	_clock = clock


func snapshot_from_properties(card: Dictionary, tdp: Dictionary) -> RefCounted:
	var snapshot := _new_snapshot()
	snapshot.gpu_identity = _read_identity(card)
	snapshot.tdp_w = _read_tdp(tdp)
	snapshot.power_profile = _read_power_profile(tdp)
	return snapshot


func invalid_snapshot(state: String, reason: String) -> RefCounted:
	var snapshot := _new_snapshot()
	snapshot.gpu_identity = _observation(state, reason)
	snapshot.tdp_w = _observation(state, reason)
	snapshot.power_profile = _observation(state, reason)
	return snapshot


func _new_snapshot() -> RefCounted:
	_generation += 1
	return PowerSnapshot.new(_generation, _timestamp_msec())


func _timestamp_msec() -> int:
	if _clock.is_valid():
		return int(_clock.call())
	return Time.get_ticks_msec()


func _observation(state: String, reason: String) -> RefCounted:
	match state:
		ObservedValue.UNAVAILABLE:
			return ObservedValue.unavailable(reason)
		ObservedValue.ERROR:
			return ObservedValue.error(reason)
		_:
			return ObservedValue.unknown(reason)


func _read_identity(card: Dictionary) -> RefCounted:
	var identity := {
		"dbus_path": String(card.get("dbus_path", "")),
		"class": String(card.get("class", "")),
		"name": String(card.get("name", "")),
		"device": String(card.get("device", "")),
	}
	if (
		identity["dbus_path"].is_empty()
		and identity["name"].is_empty()
		and identity["device"].is_empty()
	):
		return ObservedValue.unknown("gpu_identity_unavailable")
	return ObservedValue.known(identity)


func _read_tdp(properties: Dictionary) -> RefCounted:
	var raw_value: Variant = properties.get("tdp")
	if not (raw_value is int or raw_value is float):
		return ObservedValue.unknown("tdp_value_invalid")
	var value := float(raw_value)
	if not is_finite(value) or value <= 0.0:
		return ObservedValue.unknown("tdp_value_invalid")
	return ObservedValue.known(value)


func _read_power_profile(properties: Dictionary) -> RefCounted:
	var profile: Variant = properties.get("power_profile")
	if not profile is String or profile.is_empty():
		return ObservedValue.unknown("power_profile_unavailable")
	return ObservedValue.known(profile)
