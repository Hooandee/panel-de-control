from contextlib import contextmanager
from itertools import islice
import math
import time
from weakref import WeakKeyDictionary

import journal


_recent = WeakKeyDictionary()
_RESULT_FIELDS = (
    "ok", "requested_w", "applied_w", "failure_kind", "stage", "observed_profile",
)
_TARGET_FIELDS = ("pl1", "pl2", "pl3", "watts", "profile", "mode", "enabled")


def _scalar(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) and abs(value) <= 1e12 else None
    if isinstance(value, str):
        return value[:128]
    return None


def _error(exc):
    return {"type": type(exc).__name__[:64], "errno": _scalar(getattr(exc, "errno", None))}


def _fields(value, keys):
    if not isinstance(value, dict):
        return {}
    return {key: _scalar(value[key]) for key in keys if key in value}


def _observation(value):
    snapshot = {"readable": None, "surfaces": {}}
    if not isinstance(value, dict):
        return snapshot
    readable = value.get("readable")
    snapshot["readable"] = readable if isinstance(readable, bool) else None
    for surface, rails in islice(value.get("surfaces", {}).items(), 4):
        snapshot["surfaces"][str(surface)[:64]] = {
            str(rail)[:64]: _fields(reading, ("applied", "min", "max"))
            for rail, reading in islice(rails.items(), 4)
        }
    return snapshot


def _emit(sink, backend, operation, before, outcome, target, on_ac, auto_tdp, started, raised):
    result = _fields(outcome.get("result", outcome), _RESULT_FIELDS)
    if raised is not None:
        result["exception"] = _error(raised)
    payload = {
        "backend": str(getattr(backend, "name", type(backend).__name__))[:64],
        "operation": str(operation)[:64],
        "before_cached": before,
        "target": _fields(target, _TARGET_FIELDS) if isinstance(target, dict) else _scalar(target),
        "result": result,
    }
    if isinstance(on_ac, bool):
        payload["on_ac"] = on_ac
    if isinstance(auto_tdp, bool):
        payload["auto_tdp"] = auto_tdp
    failed = raised is not None or result.get("ok") is False
    now = time.monotonic()
    if failed:
        try:
            _recent.pop(backend, None)
        except (TypeError, AttributeError):
            pass
    else:
        try:
            previous = _recent.get(backend)
            if previous and previous[0] == payload and now - previous[1] < 60:
                return
            _recent[backend] = (payload.copy(), now)
        except (TypeError, AttributeError):
            pass
    payload["elapsed_ms"] = max(0, round((now - started) * 1000))
    sink.write("WARNING" if failed else "INFO", "tdp", "backend_operation", **payload)


@contextmanager
def trace_operation(
    backend, operation, *, target=None, on_ac=None, auto_tdp=None,
    observation_before=None,
):
    outcome = {}
    sink = getattr(journal, "active", None)
    if sink is None:
        yield outcome
        return
    started = time.monotonic()
    try:
        before = _observation(observation_before)
    except Exception as exc:
        before = {"observation_error": _error(exc)}
    raised = None
    try:
        yield outcome
    except BaseException as exc:
        raised = exc
        raise
    finally:
        try:
            _emit(sink, backend, operation, before, outcome, target, on_ac, auto_tdp, started, raised)
        except Exception:
            pass


def run_operation(
    backend, operation, callback, *, target=None, on_ac=None, auto_tdp=None,
    observation_before=None,
):
    with trace_operation(
        backend, operation, target=target, on_ac=on_ac,
        auto_tdp=auto_tdp, observation_before=observation_before,
    ) as trace:
        result = callback()
        try:
            if isinstance(result, dict):
                trace["result"] = result
            elif isinstance(result, bool):
                trace["result"] = {"ok": result}
            else:
                trace["result"] = {
                    key: getattr(result, key)
                    for key in _RESULT_FIELDS if hasattr(result, key)
                }
        except Exception:
            pass
        return result
