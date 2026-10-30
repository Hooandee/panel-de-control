
import pytest
import errno
import io
import sys
import time

from ambient.adapters import optimizer as opt


def test_plan_downscales_only_when_needed():
    assert opt.needs_optimization(width=3840, height=2160, target_height=800) is True
    assert opt.needs_optimization(width=1280, height=720, target_height=800) is False
    assert opt.needs_optimization(width=1920, height=1080, target_height=1080) is False


def test_commands_try_vaapi_then_software(tmp_path):
    cmds = opt.build_commands("/usr/bin/ffmpeg", "/in/a.mp4", str(tmp_path / "out.mp4"), 800)
    assert "h264_vaapi" in cmds[0] and "libx264" in cmds[1]
    for cmd in cmds:
        assert cmd[0] == "/usr/bin/ffmpeg"
        assert "-an" in cmd and "fps=30" in " ".join(cmd)
        assert cmd[-1] == str(tmp_path / "out.mp4")


def test_optimize_falls_back_to_software(tmp_path, monkeypatch):
    source = tmp_path / "in.mp4"
    source.write_bytes(b"x")
    calls = []

    def fake_run(cmd, cancel):
        calls.append(cmd)
        if "h264_vaapi" in cmd:
            return 1
        open(cmd[-1], "wb").write(b"OUT")
        return 0

    monkeypatch.setattr(opt, "_run", fake_run)
    monkeypatch.setattr(opt, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    result = opt.optimize(str(source), str(tmp_path / "cache"), 800)
    assert result.encoder == "libx264"
    assert open(result.path, "rb").read() == b"OUT"
    assert len(calls) == 2


def test_optimize_without_ffmpeg_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(opt, "find_ffmpeg", lambda: None)
    with pytest.raises(opt.OptimizeError, match="no_encoder"):
        opt.optimize(str(tmp_path / "in.mp4"), str(tmp_path), 800)


def test_optimize_all_encoders_fail(tmp_path, monkeypatch):
    (tmp_path / "in.mp4").write_bytes(b"x")
    monkeypatch.setattr(opt, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(opt, "_run", lambda cmd, cancel: 1)
    with pytest.raises(opt.OptimizeError, match="encode_failed"):
        opt.optimize(str(tmp_path / "in.mp4"), str(tmp_path / "cache"), 800)
    assert not any(p.suffix == ".mp4" for p in (tmp_path / "cache").glob("*"))


def test_cancel_stops_before_encoding(tmp_path, monkeypatch):
    import threading
    (tmp_path / "in.mp4").write_bytes(b"x")
    monkeypatch.setattr(opt, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")
    called = []
    monkeypatch.setattr(opt, "_run", lambda cmd, cancel: called.append(cmd) or 0)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(opt.OptimizeError, match="cancelled"):
        opt.optimize(str(tmp_path / "in.mp4"), str(tmp_path / "cache"), 800, cancel)
    assert called == []


def test_run_kills_a_cancelled_process(monkeypatch):
    import sys
    import threading
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    assert opt._run([sys.executable, "-c", "import time; time.sleep(30)"], cancel) == -1


def test_encoder_runs_without_deckys_bundled_libraries(monkeypatch):
    import subprocess as sp

    from ambient.adapters import optimizer

    seen = {}

    class Done:
        stderr = io.BytesIO()

        def wait(self, timeout=None):
            return 0

    def popen(command, **kwargs):
        seen.update(kwargs.get("env") or {})
        return Done()

    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIbundle")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setattr(sp, "Popen", popen)
    assert optimizer._run(["ffmpeg"], None) == 0
    assert "LD_LIBRARY_PATH" not in seen


def test_frame_rate_goes_into_the_filter_and_the_cache_name(tmp_path):
    from ambient.adapters.optimizer import build_commands, output_name

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    for command in build_commands("ffmpeg", str(source), "out.mp4", 800, 15):
        assert any("fps=15" in part for part in command)
    assert output_name(str(source), 800, 15) != output_name(str(source), 800, 30)


@pytest.mark.parametrize("message", ["No space left on device", "Disk quota exceeded"])
def test_run_stops_on_real_process_storage_error_without_blocking(message):
    code = f"import sys,time; sys.stderr.write('x' * 200000 + {message!r}); sys.stderr.flush(); time.sleep(10)"
    started = time.monotonic()
    with pytest.raises(opt.OptimizeError, match="^no_space$"):
        opt._run([sys.executable, "-c", code], None)
    assert time.monotonic() - started < 5


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EDQUOT])
@pytest.mark.parametrize("stage", ["mkdir", "encode", "replace"])
def test_optimize_cleans_partial_and_preserves_source_on_storage_error(tmp_path, monkeypatch, failure, stage):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"ORIGINAL")
    cache = tmp_path / "cache"
    monkeypatch.setattr(opt, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    def fail(*args, **kwargs):
        raise OSError(failure, "full")

    def encode(cmd, cancel):
        from pathlib import Path
        Path(cmd[-1]).write_bytes(b"PARTIAL")
        if stage == "encode":
            fail()
        return 0

    monkeypatch.setattr(opt, "_run", encode)
    if stage == "mkdir":
        monkeypatch.setattr(opt.os, "makedirs", fail)
    elif stage == "replace":
        monkeypatch.setattr(opt.os, "replace", fail)
    with pytest.raises(opt.OptimizeError, match="^no_space$"):
        opt.optimize(str(source), str(cache), 800)
    assert source.read_bytes() == b"ORIGINAL"
    assert not cache.exists() or list(cache.iterdir()) == []


def test_optimize_reuses_cached_output_without_allocating_storage(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"ORIGINAL")
    cache = tmp_path / "cache"
    cache.mkdir()
    target = cache / opt.output_name(str(source), 800)
    target.write_bytes(b"CACHED")
    monkeypatch.setattr(opt, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    def no_space(*args, **kwargs):
        raise OSError(errno.ENOSPC, "full")

    monkeypatch.setattr(opt.os, "makedirs", no_space)
    result = opt.optimize(str(source), str(cache), 800)
    assert result.encoder == "cached"
    assert target.read_bytes() == b"CACHED"


def test_ffmpeg_storage_error_removes_partial_without_trying_another_encoder(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"ORIGINAL")
    cache = tmp_path / "cache"
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(opt, "find_ffmpeg", lambda: sys.executable)

    def commands(ffmpeg, source, target, height, fps):
        script = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'PARTIAL'); sys.stderr.write('No space left on device'); sys.exit(1)"
        return [
            [ffmpeg, "-c", script, target, "-c:v", "h264_vaapi"],
            [ffmpeg, "-c", f"import pathlib; pathlib.Path({str(fallback)!r}).touch()", "-c:v", "libx264"],
        ]

    monkeypatch.setattr(opt, "build_commands", commands)
    with pytest.raises(opt.OptimizeError, match="^no_space$"):
        opt.optimize(str(source), str(cache), 800)
    assert source.read_bytes() == b"ORIGINAL"
    assert list(cache.iterdir()) == []
    assert not fallback.exists()
