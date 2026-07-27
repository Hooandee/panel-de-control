extends RefCounted

const ObservedValue = preload("res://plugins/panel-de-control/core/domain/observed_value.gd")
const PowerSnapshot = preload("res://plugins/panel-de-control/core/domain/power_snapshot.gd")

var _powerstation: Variant
var _clock: Callable
var _generation := 0


func _init(powerstation: Variant = null, clock: Callable = Callable()) -> void:
	_powerstation = powerstation
	_clock = clock


func read_snapshot() -> RefCounted:
	_generation += 1
	var snapshot := PowerSnapshot.new(_generation, _timestamp_msec())
	if _powerstation == null:
		return _invalidate(snapshot, ObservedValue.UNAVAILABLE, "powerstation_unavailable")
	if not _powerstation.is_running():
		return _invalidate(snapshot, ObservedValue.UNAVAILABLE, "powerstation_not_running")

	var gpu: Variant = _powerstation.get_gpu()
	if gpu == null:
		return _invalidate(snapshot, ObservedValue.UNAVAILABLE, "gpu_unavailable")

	var cards: Variant = gpu.get_cards()
	if not cards is Array:
		return _invalidate(snapshot, ObservedValue.ERROR, "gpu_cards_invalid")

	var integrated_cards: Array[Variant] = []
	for card in cards:
		if card != null and card.get("class") == "integrated":
			integrated_cards.append(card)

	if integrated_cards.is_empty():
		return _invalidate(snapshot, ObservedValue.UNKNOWN, "integrated_gpu_not_found")
	if integrated_cards.size() > 1:
		return _invalidate(snapshot, ObservedValue.UNKNOWN, "integrated_gpu_ambiguous")

	var card: Variant = integrated_cards[0]
	snapshot.gpu_identity = _read_identity(card)
	snapshot.tdp_w = _read_tdp(card)
	snapshot.power_profile = _read_power_profile(card)
	return snapshot


func _timestamp_msec() -> int:
	if _clock.is_valid():
		return int(_clock.call())
	return Time.get_ticks_msec()


func _invalidate(snapshot: RefCounted, state: String, reason: String) -> RefCounted:
	snapshot.gpu_identity = _observation(state, reason)
	snapshot.tdp_w = _observation(state, reason)
	snapshot.power_profile = _observation(state, reason)
	return snapshot


func _observation(state: String, reason: String) -> RefCounted:
	match state:
		ObservedValue.UNAVAILABLE:
			return ObservedValue.unavailable(reason)
		ObservedValue.ERROR:
			return ObservedValue.error(reason)
		_:
			return ObservedValue.unknown(reason)


func _read_identity(card: Variant) -> RefCounted:
	var identity := {
		"dbus_path": card.get_dbus_path(),
		"class": card.get("class"),
		"name": card.get("name"),
		"device": card.get("device"),
	}
	if (
		String(identity["dbus_path"]).is_empty()
		and String(identity["name"]).is_empty()
		and String(identity["device"]).is_empty()
	):
		return ObservedValue.unknown("gpu_identity_unavailable")
	return ObservedValue.known(identity)


func _read_tdp(card: Variant) -> RefCounted:
	if not card.supports_tdp():
		return ObservedValue.unknown("tdp_not_supported")
	var tdp: Variant = card.get("tdp")
	if not (tdp is int or tdp is float):
		return ObservedValue.unknown("tdp_value_invalid")
	var value := float(tdp)
	if not is_finite(value) or value <= 0.0:
		return ObservedValue.unknown("tdp_value_invalid")
	return ObservedValue.known(value)


func _read_power_profile(card: Variant) -> RefCounted:
	var profile: Variant = card.get("power_profile")
	if not profile is String or profile.is_empty():
		return ObservedValue.unknown("power_profile_unavailable")
	return ObservedValue.known(profile)
