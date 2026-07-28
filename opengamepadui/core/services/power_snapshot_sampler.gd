extends Node

signal snapshot_updated(snapshot: RefCounted)

const PowerStationAdapter = preload(
	"res://plugins/panel-de-control/core/adapters/powerstation_adapter.gd"
)
const ObservedValue = preload(
	"res://plugins/panel-de-control/core/domain/observed_value.gd"
)

const SERVICE := "org.shadowblip.PowerStation"
const GPU_PATH := "/org/shadowblip/Performance/GPU"
const GPU_INTERFACE := "org.shadowblip.GPU"
const CARD_INTERFACE := "org.shadowblip.GPU.Card"
const TDP_INTERFACE := "org.shadowblip.GPU.Card.TDP"
const PROPERTIES_INTERFACE := "org.freedesktop.DBus.Properties"
const CARD_PATH_PATTERN := "^/org/shadowblip/Performance/GPU/card[0-9]+$"
const MAX_CARDS := 16

enum Phase {
	IDLE,
	ENUMERATE,
	CARD_PROPERTIES,
	TDP_PROPERTIES,
}


class SystemProcessTransport extends RefCounted:
	func execute_with_pipe(
		path: String,
		arguments: PackedStringArray,
		blocking: bool
	) -> Dictionary:
		return OS.execute_with_pipe(path, arguments, blocking)

	func is_process_running(pid: int) -> bool:
		return OS.is_process_running(pid)

	func get_process_exit_code(pid: int) -> int:
		return OS.get_process_exit_code(pid)

	func kill(pid: int) -> Error:
		return OS.kill(pid)


var _transport: Variant
var _clock: Callable
var _busctl_path: String
var _interval_msec: int
var _timeout_msec: int
var _maximum_backoff_msec: int
var _maximum_output_bytes: int
var _adapter: RefCounted
var _card_path_regex := RegEx.new()

var _closed := false
var _generation := 0
var _active_generation := 0
var _next_allowed_msec := 0
var _failure_count := 0
var _latest_snapshot: RefCounted

var _phase := Phase.IDLE
var _pid := -1
var _stdio: Variant
var _stderr: Variant
var _stdout_bytes := PackedByteArray()
var _stderr_bytes := PackedByteArray()
var _launched_msec := 0

var _card_paths: Array[String] = []
var _card_index := 0
var _integrated_cards: Array[Dictionary] = []


func _init(
	transport: Variant = null,
	clock: Callable = Callable(),
	busctl_path := "/usr/bin/busctl",
	interval_msec := 5000,
	timeout_msec := 1000,
	maximum_backoff_msec := 30000,
	maximum_output_bytes := 65536
) -> void:
	_transport = transport if transport != null else SystemProcessTransport.new()
	_clock = clock
	_busctl_path = busctl_path
	_interval_msec = maxi(interval_msec, 1)
	_timeout_msec = maxi(timeout_msec, 1)
	_maximum_backoff_msec = maxi(maximum_backoff_msec, _interval_msec)
	_maximum_output_bytes = maxi(maximum_output_bytes, 1)
	_adapter = PowerStationAdapter.new(_clock)
	_card_path_regex.compile(CARD_PATH_PATTERN)
	set_process(false)


func request_snapshot() -> bool:
	if _closed or has_active_process() or _now_msec() < _next_allowed_msec:
		return false
	_generation += 1
	_active_generation = _generation
	_card_paths.clear()
	_integrated_cards.clear()
	_card_index = 0
	_phase = Phase.ENUMERATE
	set_process(true)
	if not _launch(_enumerate_arguments()):
		_finish_invalid(
			ObservedValue.UNAVAILABLE,
			"powerstation_unavailable_or_unreachable",
			true
		)
	return true


func get_latest_snapshot() -> RefCounted:
	return _latest_snapshot


func has_active_process() -> bool:
	return _pid > 0


func shutdown() -> void:
	if _closed:
		return
	_closed = true
	_generation += 1
	_stop_active_process()
	_phase = Phase.IDLE
	_latest_snapshot = null
	_adapter = null
	set_process(false)


func _process(_delta: float) -> void:
	if _closed or not has_active_process():
		return
	_drain_pipes()
	if _output_is_too_large():
		_abort_active_process()
		_finish_invalid(
			ObservedValue.ERROR,
			"busctl_output_too_large",
			true
		)
		return
	if _now_msec() - _launched_msec >= _timeout_msec:
		_abort_active_process()
		_finish_invalid(ObservedValue.ERROR, "busctl_timeout", true)
		return
	if _transport.is_process_running(_pid):
		return

	_drain_pipes()
	if _output_is_too_large():
		_abort_active_process()
		_finish_invalid(
			ObservedValue.ERROR,
			"busctl_output_too_large",
			true
		)
		return
	var completed_phase := _phase
	var completed_stdout := _stdout_bytes.get_string_from_utf8()
	var exit_code: int = _transport.get_process_exit_code(_pid)
	_close_active_pipes()
	if exit_code > 0:
		_finish_invalid(ObservedValue.ERROR, "busctl_command_failed", true)
		return
	_handle_response(completed_phase, completed_stdout)


func _handle_response(completed_phase: int, output: String) -> void:
	var parser := JSON.new()
	if parser.parse(output) != OK:
		_finish_invalid(ObservedValue.ERROR, "busctl_response_invalid", true)
		return
	var payload: Variant = parser.data
	if not payload is Dictionary:
		_finish_invalid(ObservedValue.ERROR, "busctl_response_invalid", true)
		return
	match completed_phase:
		Phase.ENUMERATE:
			_handle_enumerate(payload)
		Phase.CARD_PROPERTIES:
			_handle_card_properties(payload)
		Phase.TDP_PROPERTIES:
			_handle_tdp_properties(payload)
		_:
			_finish_invalid(ObservedValue.ERROR, "busctl_response_invalid", true)


func _handle_enumerate(payload: Dictionary) -> void:
	var data: Variant = payload.get("data")
	if (
		payload.get("type") != "ao"
		or not data is Array
		or data.size() != 1
		or not data[0] is Array
	):
		_finish_invalid(ObservedValue.ERROR, "busctl_response_invalid", true)
		return
	var raw_paths: Array = data[0]
	if raw_paths.size() > MAX_CARDS:
		_finish_invalid(ObservedValue.ERROR, "gpu_card_paths_invalid", true)
		return
	for raw_path in raw_paths:
		if (
			not raw_path is String
			or _card_path_regex.search(raw_path) == null
			or raw_path.length() > 256
		):
			_finish_invalid(ObservedValue.ERROR, "gpu_card_paths_invalid", true)
			return
		_card_paths.append(raw_path)
	if _card_paths.is_empty():
		_finish_invalid(
			ObservedValue.UNKNOWN,
			"integrated_gpu_not_found",
			false
		)
		return
	_phase = Phase.CARD_PROPERTIES
	_launch_card_properties()


func _handle_card_properties(payload: Dictionary) -> void:
	var properties := _parse_properties(payload)
	if properties.is_empty():
		_finish_invalid(ObservedValue.ERROR, "busctl_response_invalid", true)
		return
	if String(properties.get("Class", "")) == "integrated":
		_integrated_cards.append({
			"dbus_path": _card_paths[_card_index],
			"class": "integrated",
			"name": String(properties.get("Name", "")),
			"device": String(properties.get("Device", "")),
		})
	_card_index += 1
	if _card_index < _card_paths.size():
		_launch_card_properties()
		return
	if _integrated_cards.is_empty():
		_finish_invalid(
			ObservedValue.UNKNOWN,
			"integrated_gpu_not_found",
			false
		)
		return
	if _integrated_cards.size() > 1:
		_finish_invalid(
			ObservedValue.UNKNOWN,
			"integrated_gpu_ambiguous",
			false
		)
		return
	_phase = Phase.TDP_PROPERTIES
	_launch_or_finish(
		_get_all_arguments(
			_integrated_cards[0]["dbus_path"],
			TDP_INTERFACE,
		),
	)


func _handle_tdp_properties(payload: Dictionary) -> void:
	var properties := _parse_properties(payload)
	if properties.is_empty():
		_finish_invalid(ObservedValue.ERROR, "busctl_response_invalid", true)
		return
	var snapshot: RefCounted = _adapter.snapshot_from_properties(
		_integrated_cards[0],
		{
			"tdp": properties.get("TDP"),
			"power_profile": properties.get("PowerProfile"),
		}
	)
	_publish(snapshot, false)


func _parse_properties(payload: Dictionary) -> Dictionary:
	var data: Variant = payload.get("data")
	if (
		payload.get("type") != "a{sv}"
		or not data is Array
		or data.size() != 1
		or not data[0] is Dictionary
	):
		return {}
	var flattened := {}
	for property_name: Variant in data[0]:
		var wrapped: Variant = data[0][property_name]
		if not wrapped is Dictionary or not wrapped.has("data"):
			return {}
		var value: Variant = wrapped["data"]
		if value is Array and value.size() == 1:
			value = value[0]
		flattened[String(property_name)] = value
	return flattened


func _launch_card_properties() -> void:
	_launch_or_finish(
		_get_all_arguments(
			_card_paths[_card_index],
			CARD_INTERFACE,
		),
	)


func _launch_or_finish(arguments: PackedStringArray) -> bool:
	if _launch(arguments):
		return true
	_finish_invalid(
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable",
		true,
	)
	return false


func _launch(arguments: PackedStringArray) -> bool:
	var process: Dictionary = _transport.execute_with_pipe(
		_busctl_path,
		arguments,
		false
	)
	if (
		not process.has("stdio")
		or not process.has("stderr")
		or process["stdio"] == null
		or process["stderr"] == null
		or int(process.get("pid", -1)) <= 0
	):
		return false
	_stdio = process["stdio"]
	_stderr = process["stderr"]
	_pid = int(process["pid"])
	_stdout_bytes.clear()
	_stderr_bytes.clear()
	_launched_msec = _now_msec()
	return true


func _enumerate_arguments() -> PackedStringArray:
	var arguments := _base_arguments()
	arguments.append_array(PackedStringArray([
		"call",
		SERVICE,
		GPU_PATH,
		GPU_INTERFACE,
		"EnumerateCards",
	]))
	return arguments


func _get_all_arguments(path: String, interface: String) -> PackedStringArray:
	var arguments := _base_arguments()
	arguments.append_array(PackedStringArray([
		"call",
		SERVICE,
		path,
		PROPERTIES_INTERFACE,
		"GetAll",
		"s",
		interface,
	]))
	return arguments


func _base_arguments() -> PackedStringArray:
	return PackedStringArray([
		"--system",
		"--json=short",
		"--timeout=1s",
		"--auto-start=no",
		"--allow-interactive-authorization=no",
	])


func _drain_pipes() -> void:
	_drain_pipe(_stdio, _stdout_bytes)
	_drain_pipe(_stderr, _stderr_bytes)


func _drain_pipe(pipe: Variant, destination: PackedByteArray) -> void:
	while pipe != null:
		var available: int = pipe.get_length()
		if available <= 0:
			return
		var remaining := _maximum_output_bytes - destination.size()
		var requested_bytes := mini(available, remaining + 1)
		var chunk: PackedByteArray = pipe.get_buffer(requested_bytes)
		if chunk.is_empty():
			return
		destination.append_array(chunk)
		if destination.size() > _maximum_output_bytes:
			return


func _output_is_too_large() -> bool:
	return (
		_stdout_bytes.size() > _maximum_output_bytes
		or _stderr_bytes.size() > _maximum_output_bytes
	)


func _abort_active_process() -> void:
	if has_active_process() and _transport.is_process_running(_pid):
		_transport.kill(_pid)
	_close_active_pipes()


func _stop_active_process() -> void:
	if has_active_process() and _transport.is_process_running(_pid):
		_transport.kill(_pid)
	_close_active_pipes()


func _close_active_pipes() -> void:
	if _stdio != null:
		_stdio.close()
	if _stderr != null:
		_stderr.close()
	_stdio = null
	_stderr = null
	_pid = -1
	_stdout_bytes.clear()
	_stderr_bytes.clear()


func _finish_invalid(state: String, reason: String, apply_backoff: bool) -> void:
	if _adapter == null:
		return
	var snapshot: RefCounted = _adapter.invalid_snapshot(state, reason)
	_publish(snapshot, apply_backoff)


func _publish(snapshot: RefCounted, apply_backoff: bool) -> void:
	_phase = Phase.IDLE
	set_process(false)
	if _closed or _active_generation != _generation:
		return
	_latest_snapshot = snapshot
	if apply_backoff:
		_failure_count += 1
		var multiplier := 1 << mini(_failure_count, 10)
		var delay := mini(
			_interval_msec * multiplier,
			_maximum_backoff_msec
		)
		_next_allowed_msec = _now_msec() + delay
	else:
		_failure_count = 0
		_next_allowed_msec = _now_msec() + _interval_msec
	snapshot_updated.emit(snapshot)


func _now_msec() -> int:
	if _clock.is_valid():
		return int(_clock.call())
	return Time.get_ticks_msec()
