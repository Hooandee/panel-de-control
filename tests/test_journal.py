import asyncio
import json
import logging
import os
import time

import journal
from journal import Journal, JournalHandler, collect, queue_logger_handlers, read_records, trace_calls

DAY = 86_400


def _lines(directory):
    return list(read_records(directory))


def _run(j, *writes):
    j.start()
    for args, kwargs in writes:
        j.write(*args, **kwargs)
    j.stop()


def test_writes_one_json_line_per_record_in_a_daily_file(tmp_path):
    now = 1_790_000_000.0
    j = Journal(str(tmp_path), clock=lambda: now)
    _run(j, (("INFO", "log", "hello"), {"at": now - 5}), (("WARNING", "log", "careful"), {}))
    records = _lines(str(tmp_path))
    assert [(r["l"], r["m"]) for r in records] == [("I", "hello"), ("W", "careful")]
    assert all(os.path.basename(p).startswith("pdc-") for p in j.files())


def test_full_queue_drops_instead_of_blocking(tmp_path):
    j = Journal(str(tmp_path), queue_size=2)
    started = time.monotonic()
    for index in range(50):
        j.write("INFO", "log", f"line {index}")
    assert time.monotonic() - started < 0.5
    assert j.dropped == 48


def test_old_days_and_excess_size_are_deleted(tmp_path):
    now = 1_790_000_000.0
    for days_ago in (10, 3, 2):
        stamp = time.strftime("%Y%m%d", time.localtime(now - days_ago * DAY))
        (tmp_path / f"pdc-{stamp}.jsonl").write_text("x" * 600 + "\n")
    j = Journal(str(tmp_path), retention_days=7, max_total_bytes=1000, clock=lambda: now)
    _run(j, (("INFO", "log", "today"), {"at": now}))
    names = sorted(os.path.basename(p) for p in j.files())
    today = time.strftime("%Y%m%d", time.localtime(now))
    two_days = time.strftime("%Y%m%d", time.localtime(now - 2 * DAY))
    assert names == [f"pdc-{two_days}.jsonl", f"pdc-{today}.jsonl"]


def test_a_full_day_file_continues_in_the_next_segment(tmp_path):
    now = 1_790_000_000.0
    j = Journal(str(tmp_path), max_file_bytes=120, clock=lambda: now)
    _run(j, *[(("INFO", "log", f"line {i}"), {"at": now}) for i in range(6)])
    assert [r["m"] for r in _lines(str(tmp_path))] == [f"line {i}" for i in range(6)]
    assert len(j.files()) > 1


def test_repeated_calls_of_one_action_collapse_into_the_last(tmp_path):
    j = Journal(str(tmp_path), coalesce_s=1.5, clock=lambda: 200.0)
    _run(
        j,
        (("INFO", "rpc", "set_tdp_watts"), {"at": 100.0, "a": "[10]"}),
        (("INFO", "rpc", "set_tdp_watts"), {"at": 100.5, "a": "[12]"}),
        (("INFO", "rpc", "set_tdp_watts"), {"at": 101.0, "a": "[15]"}),
        (("INFO", "rpc", "set_hud_config"), {"at": 101.2, "a": "[{}]"}),
        (("INFO", "rpc", "set_tdp_watts"), {"at": 110.0, "a": "[9]"}),
    )
    calls = [(r["m"], r["a"], r.get("n", 1)) for r in _lines(str(tmp_path))]
    assert calls == [("set_tdp_watts", "[15]", 3), ("set_hud_config", "[{}]", 1), ("set_tdp_watts", "[9]", 1)]


def test_collect_sends_the_last_day_whole_and_only_key_records_before(tmp_path):
    now = 1_790_000_000.0
    j = Journal(str(tmp_path), clock=lambda: now)
    _run(
        j,
        (("INFO", "log", "Audio transition {}"), {"at": now - 3 * DAY}),
        (("INFO", "log", 'TDP transition {"requested":{"pl1":7}}'), {"at": now - 3 * DAY + 1}),
        (("WARNING", "log", "fan write failed"), {"at": now - 2 * DAY}),
        (("INFO", "rpc", "set_tdp_watts"), {"at": now - 2 * DAY + 5, "a": "[7]"}),
        (("INFO", "log", "Audio transition {}"), {"at": now - 60}),
    )
    bundle = collect(str(tmp_path), now=now)
    assert [r["m"] for r in bundle["older"]] == [
        'TDP transition {"requested":{"pl1":7}}', "fan write failed", "set_tdp_watts",
    ]
    assert [r["m"] for r in bundle["recent"]] == ["Audio transition {}"]


def test_collect_keeps_the_newest_records_within_budget(tmp_path):
    now = 1_790_000_000.0
    j = Journal(str(tmp_path), clock=lambda: now)
    _run(j, *[(("INFO", "log", f"line {i:03d}"), {"at": now - 100 + i}) for i in range(100)])
    bundle = collect(str(tmp_path), now=now, recent_bytes=200)
    assert bundle["recent"][-1]["m"] == "line 099"
    assert bundle["recent_omitted"] == 100 - len(bundle["recent"])


def test_handler_copies_log_records_with_tracebacks(tmp_path):
    j = Journal(str(tmp_path))
    j.start()
    handler = JournalHandler(j)
    handler.emit(logging.makeLogRecord({"name": "root", "levelname": "INFO", "msg": "loaded %s", "args": ("v1",)}))
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        handler.emit(logging.makeLogRecord({"name": "root", "levelname": "ERROR", "msg": "failed", "exc_info": sys.exc_info()}))
    j.stop()
    records = _lines(str(tmp_path))
    assert (records[0]["s"], records[0]["m"]) == ("log", "loaded v1")
    assert records[1]["l"] == "E" and "ValueError: boom" in records[1]["m"]


def test_queued_handlers_keep_writing_and_are_restored(tmp_path):
    logger = logging.getLogger("pdc-test-queue")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    target = logging.FileHandler(str(tmp_path / "decky.log"))
    logger.addHandler(target)
    restore = queue_logger_handlers(logger)
    assert target not in logger.handlers
    logger.info("through the queue")
    restore()
    assert logger.handlers == [target]
    target.close()
    logger.removeHandler(target)
    assert "through the queue" in (tmp_path / "decky.log").read_text()


def test_traced_calls_record_arguments_and_failures(tmp_path):
    class Plugin:
        async def set_value(self, value):
            return {"ok": value > 0, "error": "negative"}

        async def submit_report(self, text):
            return {"ok": True}

        async def get_value(self):
            return 1

        async def explode(self):
            raise RuntimeError("no")

        async def apply_all(self):
            return await self.set_value(5)

    trace_calls(Plugin, hidden_arguments=frozenset({"submit_report"}))
    j = Journal(str(tmp_path), coalesce_s=0)
    j.start()
    journal.active = j
    plugin = Plugin()
    try:
        asyncio.run(plugin.set_value(3))
        asyncio.run(plugin.set_value(-1))
        asyncio.run(plugin.submit_report("private words"))
        asyncio.run(plugin.get_value())
        asyncio.run(plugin.apply_all())
        try:
            asyncio.run(plugin.explode())
        except RuntimeError:
            pass
    finally:
        journal.active = None
        j.stop()
    records = _lines(str(tmp_path))
    assert [(r["m"], r.get("a"), r.get("r")) for r in records] == [
        ("set_value", "[3]", None),
        ("set_value", "[-1]", {"ok": False, "error": '"negative"'}),
        ("submit_report", None, None),
        ("apply_all", "[]", None),
        ("explode", "[]", {"raised": "RuntimeError"}),
    ]
    assert "private words" not in json.dumps(records)
