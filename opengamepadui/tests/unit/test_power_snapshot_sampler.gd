extends GutTest

const SAMPLER_PATH := "res://plugins/panel-de-control/core/services/power_snapshot_sampler.gd"
const ObservedValue = preload("res://plugins/panel-de-control/core/domain/observed_value.gd")


class FakeClock extends RefCounted:
	var now_msec := 0

	func now() -> int:
		return now_msec

	func advance(delta_msec: int) -> void:
		now_msec += delta_msec


class FakePipe extends RefCounted:
	var chunks: Array[PackedByteArray] = []
	var available_chunks := 1
	var closed := false

	func _init(text_chunks: Array[String]) -> void:
		for chunk in text_chunks:
			chunks.append(chunk.to_utf8_buffer())

	func get_available_bytes() -> int:
		if closed or chunks.is_empty() or available_chunks <= 0:
			return 0
		return chunks[0].size()

	func get_buffer(_length: int) -> PackedByteArray:
		if get_available_bytes() == 0:
			return PackedByteArray()
		available_chunks -= 1
		return chunks.pop_front()

	func advance() -> void:
		available_chunks += 1

	func release_all() -> void:
		available_chunks = chunks.size()

	func close() -> void:
		closed = true


class FakeTransport extends RefCounted:
	var responses: Array[Dictionary] = []
	var commands: Array[Dictionary] = []
	var killed_pids: Array[int] = []
	var _processes: Dictionary = {}
	var _next_pid := 100

	func queue_response(
		stdout_chunks: Array[String],
		stderr_chunks: Array[String] = [],
		running_checks := 1,
		exit_code := 0
	) -> void:
		responses.append({
			"stdout_chunks": stdout_chunks,
			"stderr_chunks": stderr_chunks,
			"running_checks": running_checks,
			"exit_code": exit_code,
		})

	func execute_with_pipe(
		path: String,
		arguments: PackedStringArray,
		blocking: bool
	) -> Dictionary:
		commands.append({
			"path": path,
			"arguments": arguments,
			"blocking": blocking,
		})
		if responses.is_empty():
			return {}
		var response: Dictionary = responses.pop_front()
		var pid := _next_pid
		_next_pid += 1
		var stdout := FakePipe.new(response["stdout_chunks"])
		var stderr := FakePipe.new(response["stderr_chunks"])
		_processes[pid] = {
			"stdout": stdout,
			"stderr": stderr,
			"running_checks": response["running_checks"],
			"exit_code": response["exit_code"],
			"killed": false,
		}
		return {"stdio": stdout, "stderr": stderr, "pid": pid}

	func is_process_running(pid: int) -> bool:
		var process: Dictionary = _processes.get(pid, {})
		if process.is_empty() or process["killed"]:
			return false
		(process["stdout"] as FakePipe).advance()
		(process["stderr"] as FakePipe).advance()
		if process["running_checks"] <= 0:
			(process["stdout"] as FakePipe).release_all()
			(process["stderr"] as FakePipe).release_all()
			return false
		process["running_checks"] -= 1
		return true

	func get_process_exit_code(pid: int) -> int:
		if is_process_running_without_advancing(pid):
			return -1
		var process: Dictionary = _processes.get(pid, {})
		if process.is_empty() or process["killed"]:
			return -1
		return process["exit_code"]

	func is_process_running_without_advancing(pid: int) -> bool:
		var process: Dictionary = _processes.get(pid, {})
		return (
			not process.is_empty()
			and not process["killed"]
			and process["running_checks"] > 0
		)

	func kill(pid: int) -> Error:
		var process: Dictionary = _processes.get(pid, {})
		if not process.is_empty():
			process["killed"] = true
		killed_pids.append(pid)
		return OK


func test_valid_partial_responses_select_integrated_card_and_publish_snapshot() -> void:
	var fixture := _new_fixture()
	var sampler: Node = fixture["sampler"]
	if sampler == null:
		return
	var transport: FakeTransport = fixture["transport"]
	transport.queue_response([
		'{"type":"ao","data":[["/org/shadowblip/Performance/',
		'GPU/card0","/org/shadowblip/Performance/GPU/card1"]]}',
	], [], 2, -1)
	transport.queue_response([_card_json("dedicated", "Discrete GPU", "1002:73df")])
	transport.queue_response([_card_json("integrated", "AMD Radeon Graphics", "1002:15bf")])
	transport.queue_response([_tdp_json(18.0, "balanced")])

	assert_true(sampler.request_snapshot())
	assert_false(sampler.request_snapshot(), "only one global request may be in flight")
	_pump_until_idle(sampler)

	var snapshot = sampler.get_latest_snapshot()
	assert_not_null(snapshot)
	assert_eq(snapshot.gpu_identity.value["class"], "integrated")
	assert_eq(snapshot.gpu_identity.value["device"], "1002:15bf")
	assert_eq(snapshot.tdp_w.value, 18.0)
	assert_eq(snapshot.power_profile.value, "balanced")
	assert_eq(transport.commands.size(), 4)
	for command: Dictionary in transport.commands:
		_assert_safe_command(command)
	assert_eq(
		transport.commands[0]["arguments"][-1],
		"EnumerateCards"
	)
	assert_eq(
		transport.commands[1]["arguments"][-1],
		"org.shadowblip.GPU.Card"
	)
	assert_eq(
		transport.commands[3]["arguments"][-1],
		"org.shadowblip.GPU.Card.TDP"
	)
	sampler.shutdown()


func test_timeout_kills_process_closes_pipes_and_publishes_error() -> void:
	var fixture := _new_fixture()
	var sampler: Node = fixture["sampler"]
	if sampler == null:
		return
	var transport: FakeTransport = fixture["transport"]
	var clock: FakeClock = fixture["clock"]
	transport.queue_response([], [], 100)

	assert_true(sampler.request_snapshot())
	sampler._process(0.0)
	var stdout: FakePipe = transport._processes[100]["stdout"]
	var stderr: FakePipe = transport._processes[100]["stderr"]
	clock.advance(1001)
	sampler._process(0.0)

	assert_eq(transport.killed_pids, [100])
	assert_true(stdout.closed)
	assert_true(stderr.closed)
	_assert_invalid(
		sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"busctl_timeout"
	)
	sampler.shutdown()


func test_malformed_output_backs_off_then_recovers() -> void:
	var fixture := _new_fixture(10, 100)
	var sampler: Node = fixture["sampler"]
	if sampler == null:
		return
	var transport: FakeTransport = fixture["transport"]
	var clock: FakeClock = fixture["clock"]
	transport.queue_response(["not json"])

	assert_true(sampler.request_snapshot())
	_pump_until_idle(sampler)
	_assert_invalid(
		sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"busctl_response_invalid"
	)
	assert_false(sampler.request_snapshot(), "failure must apply bounded backoff")

	clock.advance(20)
	transport.queue_response([_enumerate_json(["/org/shadowblip/Performance/GPU/card1"])])
	transport.queue_response([_card_json("integrated", "AMD Radeon Graphics", "1002:15bf")])
	transport.queue_response([_tdp_json(22.0, "performance")])
	assert_true(sampler.request_snapshot())
	_pump_until_idle(sampler)

	assert_eq(sampler.get_latest_snapshot().tdp_w.value, 22.0)
	assert_eq(sampler.get_latest_snapshot().power_profile.value, "performance")
	sampler.shutdown()


func test_command_error_and_oversized_output_fail_conservatively() -> void:
	var fixture := _new_fixture(10, 100, 64)
	var sampler: Node = fixture["sampler"]
	if sampler == null:
		return
	var transport: FakeTransport = fixture["transport"]
	var clock: FakeClock = fixture["clock"]
	transport.queue_response([], ["access denied"], 0, 1)
	assert_true(sampler.request_snapshot())
	_pump_until_idle(sampler)
	_assert_invalid(
		sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"busctl_command_failed"
	)

	clock.advance(20)
	transport.queue_response(["x".repeat(65)], [], 100)
	assert_true(sampler.request_snapshot())
	sampler._process(0.0)
	assert_eq(transport.killed_pids, [101])
	_assert_invalid(
		sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"busctl_output_too_large"
	)
	sampler.shutdown()


func test_invalid_or_excessive_card_paths_are_never_queried() -> void:
	var fixture := _new_fixture()
	var sampler: Node = fixture["sampler"]
	if sampler == null:
		return
	var transport: FakeTransport = fixture["transport"]
	transport.queue_response([_enumerate_json(["/tmp/not-a-gpu"])])
	assert_true(sampler.request_snapshot())
	_pump_until_idle(sampler)
	_assert_invalid(
		sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"gpu_card_paths_invalid"
	)
	assert_eq(transport.commands.size(), 1)
	sampler.shutdown()

	var second_fixture := _new_fixture()
	var second_sampler: Node = second_fixture["sampler"]
	if second_sampler == null:
		return
	var second_transport: FakeTransport = second_fixture["transport"]
	var paths: Array[String] = []
	for index in range(17):
		paths.append("/org/shadowblip/Performance/GPU/card%d" % index)
	second_transport.queue_response([_enumerate_json(paths)])
	assert_true(second_sampler.request_snapshot())
	_pump_until_idle(second_sampler)
	_assert_invalid(
		second_sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"gpu_card_paths_invalid"
	)
	assert_eq(second_transport.commands.size(), 1)
	second_sampler.shutdown()


func test_response_types_and_exact_card_paths_are_validated() -> void:
	var type_fixture := _new_fixture()
	var type_sampler: Node = type_fixture["sampler"]
	if type_sampler == null:
		return
	var type_transport: FakeTransport = type_fixture["transport"]
	type_transport.queue_response([JSON.stringify({
		"type": "a{sv}",
		"data": [["/org/shadowblip/Performance/GPU/card1"]],
	})])
	assert_true(type_sampler.request_snapshot())
	_pump_until_idle(type_sampler)
	_assert_invalid(
		type_sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"busctl_response_invalid"
	)
	assert_eq(type_transport.commands.size(), 1)
	type_sampler.shutdown()

	var path_fixture := _new_fixture()
	var path_sampler: Node = path_fixture["sampler"]
	if path_sampler == null:
		return
	var path_transport: FakeTransport = path_fixture["transport"]
	path_transport.queue_response([
		_enumerate_json(["/org/shadowblip/Performance/GPU/cardevil"]),
	])
	assert_true(path_sampler.request_snapshot())
	_pump_until_idle(path_sampler)
	_assert_invalid(
		path_sampler.get_latest_snapshot(),
		ObservedValue.ERROR,
		"gpu_card_paths_invalid"
	)
	assert_eq(path_transport.commands.size(), 1)
	path_sampler.shutdown()


func test_launch_failure_in_each_followup_phase_finishes_unavailable() -> void:
	var card_fixture := _new_fixture()
	var card_sampler: Node = card_fixture["sampler"]
	if card_sampler == null:
		return
	var card_transport: FakeTransport = card_fixture["transport"]
	card_transport.queue_response([
		_enumerate_json(["/org/shadowblip/Performance/GPU/card1"]),
	])
	assert_true(card_sampler.request_snapshot())
	_pump_until_idle(card_sampler)
	_assert_invalid(
		card_sampler.get_latest_snapshot(),
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable"
	)
	card_sampler.shutdown()

	var tdp_fixture := _new_fixture()
	var tdp_sampler: Node = tdp_fixture["sampler"]
	if tdp_sampler == null:
		return
	var tdp_transport: FakeTransport = tdp_fixture["transport"]
	tdp_transport.queue_response([
		_enumerate_json(["/org/shadowblip/Performance/GPU/card1"]),
	])
	tdp_transport.queue_response([
		_card_json("integrated", "AMD Radeon Graphics", "1002:15bf"),
	])
	assert_true(tdp_sampler.request_snapshot())
	_pump_until_idle(tdp_sampler)
	_assert_invalid(
		tdp_sampler.get_latest_snapshot(),
		ObservedValue.UNAVAILABLE,
		"powerstation_unavailable_or_unreachable"
	)
	tdp_sampler.shutdown()


func test_shutdown_kills_active_process_and_never_publishes_late_data() -> void:
	var fixture := _new_fixture()
	var sampler: Node = fixture["sampler"]
	if sampler == null:
		return
	var transport: FakeTransport = fixture["transport"]
	transport.queue_response([_enumerate_json([
		"/org/shadowblip/Performance/GPU/card1",
	])], [], 100)
	watch_signals(sampler)
	assert_true(sampler.request_snapshot())
	sampler._process(0.0)
	var stdout: FakePipe = transport._processes[100]["stdout"]
	var stderr: FakePipe = transport._processes[100]["stderr"]

	sampler.shutdown()
	sampler._process(0.0)

	assert_eq(transport.killed_pids, [100])
	assert_true(stdout.closed)
	assert_true(stderr.closed)
	assert_false(sampler.is_processing())
	assert_false(sampler.request_snapshot())
	assert_null(sampler.get_latest_snapshot())
	assert_signal_not_emitted(sampler, "snapshot_updated")


func _new_fixture(
	interval_msec := 5000,
	maximum_backoff_msec := 30000,
	maximum_output_bytes := 65536
) -> Dictionary:
	var sampler_script := load(SAMPLER_PATH) as GDScript
	assert_not_null(sampler_script, "the busctl sampler must exist")
	if sampler_script == null:
		return {"sampler": null}
	var transport := FakeTransport.new()
	var clock := FakeClock.new()
	var sampler := sampler_script.new(
		transport,
		clock.now,
		"/usr/bin/busctl",
		interval_msec,
		1000,
		maximum_backoff_msec,
		maximum_output_bytes
	) as Node
	add_child_autofree(sampler)
	return {"sampler": sampler, "transport": transport, "clock": clock}


func _pump_until_idle(sampler: Node) -> void:
	for _iteration in range(32):
		sampler._process(0.0)
		if not sampler.has_active_process():
			return
	fail_test("sampler did not finish its deterministic fake process")


func _assert_safe_command(command: Dictionary) -> void:
	assert_eq(command["path"], "/usr/bin/busctl")
	assert_false(command["blocking"])
	var arguments: PackedStringArray = command["arguments"]
	assert_eq(arguments.slice(0, 5), PackedStringArray([
		"--system",
		"--json=short",
		"--timeout=1s",
		"--auto-start=no",
		"--allow-interactive-authorization=no",
	]))
	assert_does_not_have(arguments, "set-property")


func _assert_invalid(snapshot: Variant, state: String, reason: String) -> void:
	assert_not_null(snapshot)
	assert_eq(snapshot.gpu_identity.state, state)
	assert_eq(snapshot.gpu_identity.reason, reason)
	assert_null(snapshot.gpu_identity.value)
	assert_eq(snapshot.tdp_w.state, state)
	assert_eq(snapshot.tdp_w.reason, reason)


func _enumerate_json(paths: Array[String]) -> String:
	return JSON.stringify({"type": "ao", "data": [paths]})


func _card_json(gpu_class: String, name: String, device: String) -> String:
	return JSON.stringify({
		"type": "a{sv}",
		"data": [{
			"Class": {"type": "s", "data": gpu_class},
			"Name": {"type": "s", "data": name},
			"Device": {"type": "s", "data": device},
		}],
	})


func _tdp_json(tdp_w: float, profile: String) -> String:
	return JSON.stringify({
		"type": "a{sv}",
		"data": [{
			"TDP": {"type": "d", "data": tdp_w},
			"PowerProfile": {"type": "s", "data": profile},
		}],
	})
