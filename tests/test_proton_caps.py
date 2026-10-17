import os

from launch.proton_caps import detect_capabilities


def _write_proton(root, compat_name, body):
    d = os.path.join(root, ".steam", "steam", "compatibilitytools.d", compat_name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "proton"), "w") as f:
        f.write(body)


def _write_builtin_proton(root, folder, body, *, official_fsr4=False):
    d = os.path.join(root, ".steam", "steam", "steamapps", "common", folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "proton"), "w") as f:
        f.write(body)
    if official_fsr4:
        contrib = os.path.join(d, "contrib")
        os.makedirs(contrib, exist_ok=True)
        with open(os.path.join(contrib, "amdxcffx64.dll"), "wb"):
            pass
    return d


def _write_compat_tool(root, folder, tool_id, body, *, protonfixes=None):
    """Write a custom compat tool whose folder name may differ from its id."""
    d = os.path.join(root, ".steam", "steam", "compatibilitytools.d", folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "proton"), "w") as f:
        f.write(body)
    if tool_id is not None:
        with open(os.path.join(d, "toolmanifest.vdf"), "w") as f:
            f.write(f'"compat_tool_name"\t\t"{tool_id}"\n')
    if protonfixes:
        pf = os.path.join(d, "protonfixes")
        os.makedirs(pf, exist_ok=True)
        for name, content in protonfixes.items():
            with open(os.path.join(pf, name), "w") as f:
                f.write(content)
    return d


PROTON_BODY = """
    def config(self):
        self.check_environment("PROTON_NO_NTSYNC", "nontsync")
        self.check_environment("PROTON_ENABLE_HDR", "hdr")
        self.check_environment("PROTON_FSR4_RDNA3_UPGRADE", "fsr4rdna3")
        self.check_environment("PROTON_PREFER_SDL", "sdlinput")
"""

def test_reads_supported_vars_from_script(tmp_path):
    _write_proton(str(tmp_path), "GE-Proton10-21", PROTON_BODY)
    caps = detect_capabilities("GE-Proton10-21", home=str(tmp_path))
    assert caps["found"] is True
    assert "PROTON_NO_NTSYNC" in caps["envs"]
    assert "PROTON_ENABLE_HDR" in caps["envs"]
    assert "PROTON_FSR4_RDNA3_UPGRADE" in caps["envs"]
    assert "PROTON_PREFER_SDL" in caps["envs"]
    # Core vars always present.
    assert "PROTON_LOG" in caps["envs"]


def test_absent_var_not_reported(tmp_path):
    _write_proton(str(tmp_path), "GE-Proton10-21", PROTON_BODY)
    caps = detect_capabilities("GE-Proton10-21", home=str(tmp_path))
    # FSR3/XeSS aren't in this script → not offered.
    assert "PROTON_FSR3_UPGRADE" not in caps["envs"]
    assert "PROTON_XESS_UPGRADE" not in caps["envs"]


def test_refreshes_official_fsr4_from_bundled_dll(tmp_path):
    install_dir = _write_builtin_proton(
        str(tmp_path),
        "Proton - Experimental",
        "# official Proton script",
    )
    caps = detect_capabilities("proton_experimental", home=str(tmp_path))
    assert "FSR4_UPGRADE" not in caps["envs"]

    _write_builtin_proton(
        str(tmp_path),
        "Proton - Experimental",
        "# updated official Proton script",
        official_fsr4=True,
    )
    caps = detect_capabilities("proton_experimental", home=str(tmp_path))
    assert "FSR4_UPGRADE" in caps["envs"]

    os.remove(os.path.join(install_dir, "contrib", "amdxcffx64.dll"))
    caps = detect_capabilities("proton_experimental", home=str(tmp_path))
    assert "FSR4_UPGRADE" not in caps["envs"]


def test_not_found_offers_nothing(tmp_path):
    # An unlocatable build offers nothing (don't surface unverified vars).
    caps = detect_capabilities("Nonexistent-Proton", home=str(tmp_path))
    assert caps["found"] is False
    assert caps["envs"] == []


def test_no_compat_tool_offers_nothing(tmp_path):
    # Native / non-Steam games (empty compat tool) get no Proton options.
    caps = detect_capabilities("", home=str(tmp_path))
    assert caps == {"envs": [], "found": False}


def test_resolves_compat_tool_id_from_manifest(tmp_path):
    # The user's case: folder "Proton-CachyOS Latest-x86_64_v3" (ProtonPlus install)
    # has id "proton-cachyos-11.0-2026-07-03" in its toolmanifest.vdf.
    _write_compat_tool(
        str(tmp_path),
        "Proton-CachyOS Latest-x86_64_v3",
        "proton-cachyos-11.0-2026-07-03",
        'self.check_environment("PROTON_USE_OPTISCALER", "optiscaler")\nFSR4_UPGRADE=1\n',
    )
    caps = detect_capabilities("proton-cachyos-11.0-2026-07-03", home=str(tmp_path))
    assert caps["found"] is True
    assert "PROTON_USE_OPTISCALER" in caps["envs"]
    assert "FSR4_UPGRADE" in caps["envs"]


def test_scans_system_wide_compat_root(tmp_path):
    # CachyOS installs Proton-CachyOS into /usr/share/steam/compatibilitytools.d.
    sys_root = os.path.join(str(tmp_path), "usr", "share", "steam", "compatibilitytools.d")
    d = os.path.join(sys_root, "Proton-CachyOS Latest")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "proton"), "w") as f:
        f.write('self.check_environment("PROTON_USE_OPTISCALER", "optiscaler")\n')
    with open(os.path.join(d, "toolmanifest.vdf"), "w") as f:
        f.write('"compat_tool_name"\t\t"proton-cachyos-11.0-2026-07-03"\n')
    caps = detect_capabilities(
        "proton-cachyos-11.0-2026-07-03", home=str(tmp_path), system_dirs=(sys_root,),
    )
    assert caps["found"] is True
    assert "PROTON_USE_OPTISCALER" in caps["envs"]


def test_scans_protonfixes_for_env_vars(tmp_path):
    # Modern builds moved upscaler handling into protonfixes (e.g. upscalers.py).
    _write_compat_tool(
        str(tmp_path),
        "Proton-CachyOS Latest",
        "proton-cachyos-11.0-2026-07-03",
        "# proton script",
        protonfixes={
            "upscalers.py": (
                "fsr4_version = get_version(env, 'PROTON_FSR4_UPGRADE', 'default')\n"
                "optiscaler = get_version(env, 'PROTON_USE_OPTISCALER', 'default')\n"
            ),
        },
    )
    caps = detect_capabilities("proton-cachyos-11.0-2026-07-03", home=str(tmp_path))
    assert caps["found"] is True
    assert "PROTON_FSR4_UPGRADE" in caps["envs"]
    assert "PROTON_USE_OPTISCALER" in caps["envs"]


def test_reports_rdna3_upgrade_when_referenced(tmp_path):
    # Older builds (e.g. CachyOS 10.x / GE-Proton) still reference the RDNA3 var.
    _write_proton(
        str(tmp_path),
        "Proton-CachyOS Latest",
        'self.check_environment("PROTON_FSR4_RDNA3_UPGRADE", "fsr4rdna3")\n',
    )
    caps = detect_capabilities("Proton-CachyOS Latest", home=str(tmp_path))
    assert caps["found"] is True
    assert "PROTON_FSR4_RDNA3_UPGRADE" in caps["envs"]


def test_removed_var_not_reported_when_absent(tmp_path):
    # CachyOS 11.0 removed PROTON_ENABLE_HDR; a build that no longer references it
    # must not report it — the scan reports what the build actually supports.
    _write_proton(
        str(tmp_path),
        "Proton-CachyOS Latest",
        'self.check_environment("PROTON_USE_OPTISCALER", "optiscaler")\n',
    )
    caps = detect_capabilities("Proton-CachyOS Latest", home=str(tmp_path))
    assert caps["found"] is True
    assert "PROTON_USE_OPTISCALER" in caps["envs"]
    assert "PROTON_ENABLE_HDR" not in caps["envs"]


def test_reports_short_upscaler_names_from_script(tmp_path):
    # CachyOS 11.0 exposes short names (FSR4_UPGRADE) via the proton script.
    _write_proton(
        str(tmp_path),
        "Proton-CachyOS Latest",
        'FSR4_UPGRADE=1\n',
    )
    caps = detect_capabilities("Proton-CachyOS Latest", home=str(tmp_path))
    assert caps["found"] is True
    assert "FSR4_UPGRADE" in caps["envs"]


def _write_system_proton(system_dir, folder, body):
    d = os.path.join(system_dir, folder)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "proton"), "w") as f:
        f.write(body)


def test_reads_system_wide_compat_tool(tmp_path):
    system_dir = str(tmp_path / "usr-share-steam-compat")
    _write_system_proton(system_dir, "proton-cachyos-11.0-arm64", PROTON_BODY)
    caps = detect_capabilities(
        "proton-cachyos-11.0-arm64", home=str(tmp_path / "home"), system_dirs=(system_dir,),
    )
    assert caps["found"] is True
    assert "PROTON_ENABLE_HDR" in caps["envs"]


def test_user_compat_tool_wins_over_system_copy(tmp_path):
    home = str(tmp_path / "home")
    system_dir = str(tmp_path / "system")
    _write_proton(home, "proton-cachyos", PROTON_BODY)
    _write_system_proton(system_dir, "proton-cachyos", "# stripped system build")
    caps = detect_capabilities("proton-cachyos", home=home, system_dirs=(system_dir,))
    assert "PROTON_ENABLE_HDR" in caps["envs"]


def test_arm64_builtin_never_reads_the_x86_build(tmp_path):
    _write_builtin_proton(str(tmp_path), "Proton - Experimental", PROTON_BODY)
    caps = detect_capabilities("proton-experimental-arm64", home=str(tmp_path), system_dirs=())
    assert caps == {"envs": [], "found": False}


def test_arm64_builtins_read_valves_arm64_folders(tmp_path):
    _write_builtin_proton(str(tmp_path), "Proton Experimental (ARM64)", PROTON_BODY)
    _write_builtin_proton(str(tmp_path), "Proton 11.0 (ARM64)", PROTON_BODY)
    for name in ("proton-experimental-arm64", "proton_11-arm64"):
        caps = detect_capabilities(name, home=str(tmp_path), system_dirs=())
        assert caps["found"] is True and "PROTON_LOG" in caps["envs"], name
    assert detect_capabilities("proton_hotfix-arm64", home=str(tmp_path), system_dirs=())["found"] is False
