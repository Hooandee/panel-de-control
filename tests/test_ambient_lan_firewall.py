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


def test_falls_back_to_the_default_zone_and_reports_a_refusal():
    calls = []
    answers = [("--state", (0, "running")), ("ip", (1, "")), ("--get-default-zone", (0, "public")), ("--zone=public", (13, ""))]
    assert lan_firewall.open_port(41000, "10.0.0.2", 600, run=runner(answers, calls), which=lambda _: "/usr/bin/firewall-cmd") == "failed:public:13"
