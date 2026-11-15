from gpu_support import _make_plugin
import os
from tdp.arm_levels import ArmPerformanceLevels


LITTLE = "307200 441600 556800 672000 787200 902400 1017600 1113600 1228800 1344000 1459200 1555200 1670400 1785600 1900800 2016000"


BIG = "499200 614400 729600 844800 940800 1056000 1171200 1286400 1401600 1536000 1651200 1785600 1920000 2054400 2188800 2323200 2457600 2592000 2707200 2803200"


PRIME = "595200 729600 864000 998400 1132800 1248000 1363200 1478400 1593600 1708800 1843200 1977600 2092800 2227200 2342400 2476800 2592000 2726400 2841600 2956800"


GPU = "220000000 295000000 348000000 401000000 475000000 550000000 615000000 680000000"


def _thor(tmp_path, armada_balanced=True):
    root = str(tmp_path)
    _policy(root, 0, LITTLE, current_max=1555200 if armada_balanced else None)
    _policy(root, 3, BIG, current_max=2054400 if armada_balanced else None)
    _policy(root, 7, PRIME, "3187200", current_max=2092800 if armada_balanced else None)
    gpu = "sys/class/devfreq/3d00000.gpu"
    _write(root, f"{gpu}/available_frequencies", GPU)
    _write(root, f"{gpu}/min_freq", 220000000)
    _write(root, f"{gpu}/max_freq", 680000000)
    _write(root, f"{gpu}/governor", "simple_ondemand")
    return root


def _caps(root):
    return (
        _read(root, "sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq"),
        _read(root, "sys/devices/system/cpu/cpufreq/policy3/scaling_max_freq"),
        _read(root, "sys/devices/system/cpu/cpufreq/policy7/scaling_max_freq"),
        _read(root, "sys/class/devfreq/3d00000.gpu/max_freq"),
    )


def _arm_plugin(tmp_path, monkeypatch):
    import tdp.factory as factory

    p, _ = _make_plugin(tmp_path, monkeypatch)
    root = _thor(tmp_path / "sys-root")
    monkeypatch.setattr(
        factory, "select_backend", lambda device, **kw: ArmPerformanceLevels(root=root)
    )
    p._init()
    return p, root


def _write(root, rel, value):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def _read(root, rel):
    with open(os.path.join(root, rel)) as handle:
        return int(handle.read())


def _policy(root, number, table, boost="", current_max=None):
    base = f"sys/devices/system/cpu/cpufreq/policy{number}"
    _write(root, f"{base}/related_cpus", f"{number}\n")
    values = [int(v) for v in table.split()] + [int(v) for v in boost.split()]
    _write(root, f"{base}/scaling_available_frequencies", table)
    _write(root, f"{base}/scaling_boost_frequencies", boost)
    _write(root, f"{base}/cpuinfo_min_freq", min(values))
    _write(root, f"{base}/cpuinfo_max_freq", max(values))
    _write(root, f"{base}/scaling_min_freq", min(values))
    _write(root, f"{base}/scaling_max_freq", current_max or max(values))
    return base
