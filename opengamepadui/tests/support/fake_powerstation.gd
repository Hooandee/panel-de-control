extends RefCounted


class WriteTrap extends RefCounted:
	var count := 0

	func record() -> void:
		count += 1
		push_error("PowerStationAdapter attempted to write through the read-only fake")


class FakeGpuCard extends RefCounted:
	var _data: Dictionary
	var _write_trap: WriteTrap

	func _init(data: Dictionary, write_trap: WriteTrap) -> void:
		_data = data
		_write_trap = write_trap

	func _get(property: StringName) -> Variant:
		return _data.get(String(property), null)

	func _set(_property: StringName, _value: Variant) -> bool:
		_write_trap.record()
		return true

	func get_dbus_path() -> String:
		return _data.get("dbus_path", "")

	func supports_tdp() -> bool:
		return _data.get("supports_tdp", false)

	func set_tdp(_value: Variant) -> void:
		_write_trap.record()

	func set_power_profile(_value: Variant) -> void:
		_write_trap.record()


class FakeGpu extends RefCounted:
	var _cards: Array
	var _write_trap: WriteTrap

	func _init(cards: Array, write_trap: WriteTrap) -> void:
		_write_trap = write_trap
		for card_data in cards:
			_cards.append(FakeGpuCard.new(card_data, write_trap))

	func get_cards() -> Array:
		return _cards

	func _set(_property: StringName, _value: Variant) -> bool:
		_write_trap.record()
		return true

	func set_tdp(_value: Variant) -> void:
		_write_trap.record()

	func set_power_profile(_value: Variant) -> void:
		_write_trap.record()


var running := true
var expose_gpu := true
var _gpu: FakeGpu
var _write_trap := WriteTrap.new()


func _init(cards: Array = [], is_running := true, has_gpu := true) -> void:
	running = is_running
	expose_gpu = has_gpu
	_gpu = FakeGpu.new(cards, _write_trap)


func is_running() -> bool:
	return running


func get_gpu() -> Variant:
	if not expose_gpu:
		return null
	return _gpu


func _set(_property: StringName, _value: Variant) -> bool:
	_write_trap.record()
	return true


func set_tdp(_value: Variant) -> void:
	_write_trap.record()


func set_power_profile(_value: Variant) -> void:
	_write_trap.record()


func write_attempts() -> int:
	return _write_trap.count
