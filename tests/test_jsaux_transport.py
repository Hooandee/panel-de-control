import os
import sys
import termios
import threading

import pytest

from accessories.jsaux_pixel import codec, detect, transport

BAUD = getattr(termios, "B1000000", termios.B38400)


def _fake_usb_serial(root, bus_port="7-1", vendor="1a86", product="7523", tty="ttyUSB0"):
    device = root / "devices/pci0000:00/0000:09:00.4/usb7" / bus_port
    iface = device / f"{bus_port}:1.0" / tty
    iface.mkdir(parents=True)
    (device / "idVendor").write_text(vendor + "\n")
    (device / "idProduct").write_text(product + "\n")
    links = root / "bus/usb-serial/devices"
    links.mkdir(parents=True, exist_ok=True)
    (links / tty).symlink_to(iface)
    return root


def test_finds_the_ch340_and_its_supply_strength(tmp_path):
    panel = detect.find_panel(_fake_usb_serial(tmp_path))
    assert panel == detect.PanelPort(dev="/dev/ttyUSB0", bus_port="7-1", strong_supply=True)


@pytest.mark.parametrize("bus_port,strong", [("5-1", True), ("1-2", True), ("3-2", False), ("7-1.4", False)])
def test_supply_strength_follows_the_official_strong_port_list(tmp_path, bus_port, strong):
    assert detect.find_panel(_fake_usb_serial(tmp_path, bus_port=bus_port)).strong_supply is strong


def test_other_usb_serial_adapters_are_ignored(tmp_path):
    assert detect.find_panel(_fake_usb_serial(tmp_path, vendor="0403", product="6001")) is None
    assert detect.find_panel(tmp_path / "missing") is None


def test_lists_other_processes_holding_the_port(tmp_path):
    for pid, comm, target in [("100", "jsaux-matrix-dae", "/dev/ttyUSB0"), ("200", "bash", "/dev/null")]:
        fd = tmp_path / pid / "fd"
        fd.mkdir(parents=True)
        (fd / "3").symlink_to(target)
        (tmp_path / pid / "comm").write_text(comm + "\n")
    (tmp_path / "self").mkdir()
    assert detect.port_holders("/dev/ttyUSB0", proc_root=tmp_path, own_pid=999) == [(100, "jsaux-matrix-dae")]


class _FakePanel:
    """Answers each received frame like the firmware: echo with payload 1, or nothing."""

    def __init__(self, master, mute_commands=()):
        self.master, self.mute, self.received = master, set(mute_commands), []
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        buf = b""
        while True:
            try:
                data = os.read(self.master, 4096)
            except OSError:
                return
            buf += data
            while len(buf) >= 8 and buf[:2] == b"DY":
                size = 6 + int.from_bytes(buf[4:6], "big") + 2
                if len(buf) < size:
                    break
                frame, buf = buf[:size], buf[size:]
                self.received.append(frame)
                if frame[3] in self.mute:
                    continue
                known = not (frame[3] == codec.Cmd.ANIMATION and frame[6] > 3)
                os.write(self.master, codec.frame(frame[2], frame[3], b"\x01" if known else b"\x00"))


@pytest.fixture
def pty_panel():
    master, slave = os.openpty()
    path = os.ttyname(slave)
    # Linux hangs up the master once no slave fd is open, which would end the fake panel's reads.
    yield master, path
    os.close(slave)
    os.close(master)


def test_request_returns_the_panel_echo(pty_panel):
    master, path = pty_panel
    _FakePanel(master)
    link = transport.Transport(path, baud=BAUD)
    link.open()
    try:
        assert transport.handshake(link)
        reply = link.request(codec.frame(1, codec.Cmd.GIF_END, b"\x01"), timeout=1.0)
        assert codec.is_ack(reply, 1, codec.Cmd.GIF_END)
    finally:
        link.close()


def test_silence_times_out_without_raising(pty_panel):
    master, path = pty_panel
    _FakePanel(master, mute_commands={codec.Cmd.POWER, codec.Cmd.ANIMATION})
    link = transport.Transport(path, baud=BAUD)
    link.open()
    try:
        assert link.request(codec.frame(1, codec.Cmd.POWER, b"\x01"), timeout=0.2) is None
        assert not transport.handshake(link, timeout=0.2)
    finally:
        link.close()


def test_send_writes_without_waiting_for_a_reply(pty_panel):
    master, path = pty_panel
    fake = _FakePanel(master, mute_commands={codec.Cmd.BRIGHTNESS})
    link = transport.Transport(path, baud=BAUD)
    link.open()
    try:
        link.send(codec.frame(1, codec.Cmd.BRIGHTNESS, b"\x28"))
        assert link.request(codec.frame(1, codec.Cmd.POWER, b"\x01"), timeout=1.0)
        assert fake.received[0] == codec.frame(1, codec.Cmd.BRIGHTNESS, b"\x28")
    finally:
        link.close()


def test_closed_link_reports_a_transport_error():
    link = transport.Transport("/dev/does-not-exist", baud=BAUD)
    with pytest.raises(transport.TransportError):
        link.open()
    with pytest.raises(transport.TransportError):
        link.request(b"DY", timeout=0.1)


def test_handshake_is_a_rejected_animation_that_leaves_the_screen_alone(pty_panel):
    master, path = pty_panel
    fake = _FakePanel(master)
    link = transport.Transport(path, baud=BAUD)
    link.open()
    try:
        assert transport.handshake(link)
        assert fake.received == [codec.frame(1, codec.Cmd.ANIMATION, b"\x0c")]
    finally:
        link.close()


def test_is_reply_accepts_nak_but_not_corruption():
    assert codec.is_reply(codec.frame(1, codec.Cmd.ANIMATION, b"\x00"), 1, codec.Cmd.ANIMATION)
    assert not codec.is_reply(codec.frame(1, codec.Cmd.POWER, b"\x00"), 1, codec.Cmd.ANIMATION)
    assert not codec.is_reply(codec.frame(1, codec.Cmd.ANIMATION, b"\x00")[:-1] + b"\x00", 1, codec.Cmd.ANIMATION)


def test_two_links_cannot_hold_the_panel_at_once(pty_panel, tmp_path):
    master, path = pty_panel
    _FakePanel(master)
    first = transport.Transport(path, baud=BAUD, lock_path=tmp_path / "pixel.lock")
    second = transport.Transport(path, baud=BAUD, lock_path=tmp_path / "pixel.lock")
    first.open()
    try:
        with pytest.raises(transport.TransportError):
            second.open()
    finally:
        first.close()
    second.open()
    second.close()


def test_a_vanished_panel_is_a_transport_error_and_closes_the_link(pty_panel, monkeypatch):
    import termios

    _master, path = pty_panel
    link = transport.Transport(path, baud=BAUD)
    link.open()

    def gone(*_args):
        raise termios.error(5, "Input/output error")

    monkeypatch.setattr(transport.termios, "tcflush", gone)
    with pytest.raises(transport.TransportError):
        link.send(b"DY")
    assert link.is_open is False


def test_each_plug_in_and_boot_gets_its_own_usb_session(tmp_path, monkeypatch):
    root = _fake_usb_serial(tmp_path)
    device = root / "devices/pci0000:00/0000:09:00.4/usb7/7-1"
    (device / "busnum").write_text("7\n")
    (device / "devnum").write_text("5\n")
    boot = tmp_path / "boot_id"
    boot.write_text("aaaa\n")
    monkeypatch.setattr(detect, "_BOOT_ID", boot)
    first = detect.find_panel(root).session
    assert first == "7-1:7:5:aaaa"
    boot.write_text("bbbb\n")
    assert detect.find_panel(root).session != first


@pytest.fixture
def without_termios(monkeypatch):
    import importlib

    from accessories.jsaux_pixel import serial_tty

    monkeypatch.setitem(sys.modules, "termios", None)
    yield importlib.reload(serial_tty)
    monkeypatch.undo()
    importlib.reload(serial_tty)


def test_loads_without_termios(without_termios):
    # Decky Loader 3.3 embeds a Python without termios; the plugin must still start.
    shim = without_termios
    assert shim.B1000000 == 0o010010
    assert issubclass(shim.error, Exception)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="libc termios layout is Linux's")
def test_libc_fallback_configures_a_tty(without_termios):
    shim = without_termios
    master, slave = os.openpty()
    try:
        attrs = shim.tcgetattr(slave)
        attrs[0] = shim.IGNPAR
        attrs[2] = shim.CS8 | shim.CREAD | shim.CLOCAL
        attrs[4] = attrs[5] = shim.B1000000
        attrs[6][shim.VMIN] = 0
        shim.tcsetattr(slave, shim.TCSANOW, attrs)
        shim.tcflush(slave, shim.TCIFLUSH)
        again = shim.tcgetattr(slave)
        assert again[0] == shim.IGNPAR
        assert again[4] == shim.B1000000
    finally:
        os.close(master)
        os.close(slave)
