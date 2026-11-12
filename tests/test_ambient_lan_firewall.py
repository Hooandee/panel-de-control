from ambient.adapters import lan_firewall


def runner(answers, calls):
    def run(command):
        calls.append(list(command))
        for prefix, answer in answers:
            if command[1:2] == [prefix] or (command[0] == "ip" and prefix == "ip"):
                return answer
        return 0, ""
    return run


def test_does_nothing_without_firewalld_or_when_it_is_stopped():
    calls = []
    assert lan_firewall.open_port(41000, "192.168.1.5", 600, run=runner([], calls), which=lambda _: None) == "none"
    assert calls == []
    assert lan_firewall.open_port(41000, "192.168.1.5", 600, run=runner([("--state", (252, "not running"))], calls), which=lambda _: "/usr/bin/firewall-cmd") == "inactive"
    assert not any("--add-port=41000/tcp" in part for call in calls for part in call)


def test_opens_the_share_port_for_a_while_in_the_zone_of_the_lan_interface_only_at_runtime():
    calls = []
    answers = [
        ("--state", (0, "running")),
        ("ip", (0, "2: wlan0    inet 192.168.1.5/24 brd 192.168.1.255 scope global wlan0\n3: waydroid0    inet 192.168.240.1/24 scope global waydroid0")),
        ("--get-zone-of-interface=wlan0", (0, "home")),
    ]
    result = lan_firewall.open_port(41000, "192.168.1.5", 600, run=runner(answers, calls), which=lambda _: "/usr/bin/firewall-cmd")
    assert result == "opened:home"
    assert calls[-1] == ["/usr/bin/firewall-cmd", "--zone=home", "--add-port=41000/tcp", "--timeout=600s"]
    assert not any("--permanent" in part for call in calls for part in call)


def test_never_takes_over_a_port_someone_else_already_opened():
    calls = []
    answers = [("--state", (0, "running")), ("ip", (1, "")), ("--get-default-zone", (0, "public")), ("--zone=public", (0, "yes"))]
    assert lan_firewall.open_port(41000, "10.0.0.2", 600, run=runner(answers, calls), which=lambda _: "/usr/bin/firewall-cmd") == "already_open"
    assert not any(part.startswith("--add-port") for call in calls for part in call)


def test_falls_back_to_the_default_zone_and_reports_a_refusal():
    calls = []
    answers = [("--state", (0, "running")), ("ip", (1, "")), ("--get-default-zone", (0, "public")), ("--zone=public", (13, ""))]
    assert lan_firewall.open_port(41000, "10.0.0.2", 600, run=runner(answers, calls), which=lambda _: "/usr/bin/firewall-cmd") == "failed:public:13"


def test_removes_the_rule_when_the_share_ends_early():
    calls = []
    lan_firewall.close_port(41000, "home", run=lambda c: calls.append(list(c)) or (0, ""), which=lambda _: "/usr/bin/firewall-cmd")
    assert calls == [["/usr/bin/firewall-cmd", "--zone=home", "--remove-port=41000/tcp"]]


def test_a_live_stream_link_is_not_read():
    from ambient.adapters import remote_sources

    class Response:
        headers = {"Content-Type": "audio/mpeg"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, size):
            raise AssertionError("the stream must not be read")

    assert remote_sources.fetch_head("https://radio.test/live.m3u", opener=lambda request, timeout: Response()) == ""


def test_a_playlist_served_as_audio_mpegurl_is_still_read():
    from ambient.adapters import remote_sources

    class Response:
        headers = {"Content-Type": "audio/x-mpegurl"}
        parts = [b"#EXTM3U\n"]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, size):
            return self.parts.pop(0) if self.parts else b""

    assert remote_sources.fetch_head("https://lists.test/tv.m3u", opener=lambda request, timeout: Response()) == "#EXTM3U\n"


def test_a_rule_opened_after_the_share_ended_is_closed_at_once(tmp_path, monkeypatch):
    from ambient.service import AmbientService

    service = AmbientService(state_dir=str(tmp_path / "state"), cache_dir=str(tmp_path / "cache"), home=str(tmp_path))
    closed = []
    monkeypatch.setattr(lan_firewall, "open_port", lambda port, host, seconds: "opened:home")
    monkeypatch.setattr(lan_firewall, "close_port", lambda port, zone: closed.append((port, zone)))
    service._open_share_firewall("http://192.168.1.5:41000/s/token/", 600)
    assert closed == [(41000, "home")] and service._share_rule is None
    service.close()


def test_a_stream_sent_as_octet_stream_is_read_for_a_few_seconds_at_most(monkeypatch):
    from ambient.adapters import remote_sources

    clock = [0.0]
    monkeypatch.setattr(remote_sources.time, "monotonic", lambda: clock[0])

    class Trickle:
        headers = {"Content-Type": "application/octet-stream"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read1(self, size):
            clock[0] += 1.0
            return b"x" * 10

    text = remote_sources.fetch_head("https://radio.test/live", opener=lambda request, timeout: Trickle())
    assert len(text) == 30
