"""Shared serialized /proc/acpi/call caller. Synthetic node via tmp_path."""
import os

import acpi_call


def _mk(root):
    d = os.path.join(root, "proc/acpi")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "call")
    with open(p, "w") as f:
        f.write("not called")
    return p


def test_call_writes_command_and_reads_result(tmp_path):
    p = _mk(tmp_path)
    out = acpi_call.serialized_call(p, r"\_SB.GZFD.WMAB 0x00 0x05 b00000000")
    assert out is not None


def test_call_serialized_under_the_module_lock(tmp_path):
    p = _mk(tmp_path)
    order = []

    real = acpi_call._LOCK

    class TracingLock:
        def __enter__(self):
            order.append("enter")
            return real.__enter__()

        def __exit__(self, *a):
            order.append("exit")
            return real.__exit__(*a)

    acpi_call._LOCK = TracingLock()
    try:
        acpi_call.serialized_call(p, "x")
    finally:
        acpi_call._LOCK = real
    assert order == ["enter", "exit"]


def test_available_true_when_node_writable(tmp_path):
    _mk(tmp_path)
    assert acpi_call.available(root=str(tmp_path)) is True


def test_available_false_when_absent(tmp_path):
    assert acpi_call.available(root=str(tmp_path)) is False
