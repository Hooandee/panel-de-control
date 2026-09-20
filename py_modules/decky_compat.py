import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urlparse


_AFFECTED_VERSION = "v3.2.6"
_RECOVERY_EVALUATION_TIMEOUT_S = 12.0
_RECOVERY_IMPORT_TIMEOUT_MS = 4_000
_SHARED_TITLES = frozenset(
    {"SharedJSContext", "Steam Shared Context presented by Valve™", "Steam", "SP"}
)
_PROBE_SCRIPT = """
(() => {
  const app = window.App;
  let beforeLoginReady = false;
  try {
    beforeLoginReady = app?.BFinishedInitBeforeLogin?.() === true;
  } catch (_) {}
  return {
    decky_has_loaded: window.deckyHasLoaded === true,
    decky_backend: typeof window.DeckyBackend === "object" && window.DeckyBackend !== null,
    decky_backend_absent: typeof window.DeckyBackend === "undefined",
    decky_plugin_loader: typeof window.DeckyPluginLoader === "object" && window.DeckyPluginLoader !== null,
    decky_plugin_loader_absent: typeof window.DeckyPluginLoader === "undefined",
    decky_auth_token: Boolean(window.deckyAuthToken),
    decky_auth_token_absent: typeof window.deckyAuthToken === "undefined",
    dfl: Boolean(window.DFL),
    dfl_absent: typeof window.DFL === "undefined",
    sp_react: Boolean(window.SP_REACT),
    sp_react_absent: typeof window.SP_REACT === "undefined",
    app: Boolean(app),
    stage_one: typeof app?.BFinishedInitStageOne === "function",
    stage_one_absent: typeof app?.BFinishedInitStageOne === "undefined",
    before_login: typeof app?.BFinishedInitBeforeLogin === "function",
    before_login_ready: beforeLoginReady,
  };
})()
"""


@dataclass(frozen=True)
class FrontendState:
    decky_has_loaded: bool
    decky_backend: bool
    decky_backend_absent: bool
    decky_plugin_loader: bool
    decky_plugin_loader_absent: bool
    decky_auth_token: bool
    decky_auth_token_absent: bool
    dfl: bool
    dfl_absent: bool
    sp_react: bool
    sp_react_absent: bool
    app: bool
    stage_one: bool
    stage_one_absent: bool
    before_login: bool
    before_login_ready: bool


@dataclass(frozen=True)
class RecoveryResult:
    status: str
    attempted: bool = False
    detail: str | None = None


def is_affected_version(decky_version: str) -> bool:
    return decky_version == _AFFECTED_VERSION


def _is_shared_target(target: dict) -> bool:
    if target.get("title") not in _SHARED_TITLES:
        return False
    url = str(target.get("url", ""))
    if not (
        url.startswith("https://steamloopback.host/routes/")
        or url == "https://steamloopback.host/index.html"
    ):
        return False
    websocket_url = urlparse(str(target.get("webSocketDebuggerUrl", "")))
    return (
        websocket_url.scheme == "ws"
        and websocket_url.hostname in {"127.0.0.1", "localhost"}
        and websocket_url.port == 8080
    )


def _state_status(state: FrontendState) -> str:
    if state.decky_backend and state.decky_plugin_loader:
        return "already_loaded"
    if not all(
        (
            state.decky_backend_absent,
            state.decky_plugin_loader_absent,
            state.decky_auth_token_absent,
            state.dfl_absent,
            state.sp_react_absent,
        )
    ):
        return "ambiguous_state"
    if state.stage_one:
        return "legacy_api_available"
    if not state.stage_one_absent:
        return "ambiguous_state"
    if state.app and not state.before_login:
        return "unsupported_api"
    if (
        state.decky_has_loaded
        and state.app
        and state.before_login
        and state.before_login_ready
    ):
        return "recoverable"
    return "waiting"


def build_recovery_script() -> str:
    script = r"""
(async () => {
  const recoveryKey = "__pdcDecky326Recovery";
  const importTimeoutMs = __PDC_IMPORT_TIMEOUT_MS__;
  if (window[recoveryKey]) return await window[recoveryKey];

  const recovery = (async () => {
    const app = window.App;
    let ready = false;
    try {
      ready = app?.BFinishedInitBeforeLogin?.() === true;
    } catch (_) {}
    const stateIsExact =
      window.deckyHasLoaded === true &&
      typeof window.DeckyBackend === "undefined" &&
      typeof window.DeckyPluginLoader === "undefined" &&
      typeof window.deckyAuthToken === "undefined" &&
      typeof window.DFL === "undefined" &&
      typeof window.SP_REACT === "undefined" &&
      Boolean(app) &&
      typeof app.BFinishedInitStageOne === "undefined" &&
      typeof app.BFinishedInitBeforeLogin === "function" &&
      ready;
    if (!stateIsExact) return { status: "state_changed" };

    const stageOneCompat = function () {
      return app.BFinishedInitBeforeLogin();
    };
    Object.defineProperty(stageOneCompat, "__pdcDecky326Compat", { value: true });
    Object.defineProperty(app, "BFinishedInitStageOne", {
      configurable: true,
      enumerable: false,
      value: stageOneCompat,
    });

    try {
      await new Promise((resolve) => setTimeout(resolve, 250));
      const loaded = () =>
        typeof window.DeckyBackend === "object" &&
        window.DeckyBackend !== null &&
        typeof window.DeckyPluginLoader === "object" &&
        window.DeckyPluginLoader !== null;
      if (!loaded()) {
        const importBundle = import(
          `http://localhost:1337/frontend/index.js?v=v3.2.6&pdc-compat=${Date.now()}`
        );
        let importTimer;
        const importDeadline = new Promise((_, reject) => {
          importTimer = setTimeout(
            () => reject(new Error("import_timeout")),
            importTimeoutMs
          );
        });
        try {
          await Promise.race([importBundle, importDeadline]);
        } finally {
          clearTimeout(importTimer);
        }
      }
      for (let attempt = 0; attempt < 50 && !loaded(); attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      return {
        status: loaded() ? "recovered" : "postcondition_failed",
        decky_backend: typeof window.DeckyBackend === "object",
        decky_plugin_loader: typeof window.DeckyPluginLoader === "object",
      };
    } catch (error) {
      return { status: "import_failed", detail: String(error?.message || error) };
    } finally {
      if (app.BFinishedInitStageOne === stageOneCompat) {
        delete app.BFinishedInitStageOne;
      }
    }
  })();

  Object.defineProperty(window, recoveryKey, {
    configurable: true,
    enumerable: false,
    value: recovery,
  });
  try {
    return await recovery;
  } finally {
    if (window[recoveryKey] === recovery) delete window[recoveryKey];
  }
})()
"""
    return script.replace(
        "__PDC_IMPORT_TIMEOUT_MS__", str(_RECOVERY_IMPORT_TIMEOUT_MS)
    )


class LocalCdpTransport:
    def __init__(self, timeout_s: float = _RECOVERY_EVALUATION_TIMEOUT_S):
        self._timeout_s = timeout_s

    async def list_targets(self) -> list[dict]:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=min(self._timeout_s, 3.0))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("http://127.0.0.1:8080/json/list") as response:
                response.raise_for_status()
                value = await response.json()
        if not isinstance(value, list):
            raise ValueError("invalid CDP target list")
        return value

    async def _evaluate(self, target: dict, expression: str, await_promise: bool):
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=self._timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(target["webSocketDebuggerUrl"]) as websocket:
                await websocket.send_json(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": expression,
                            "awaitPromise": await_promise,
                            "returnByValue": True,
                        },
                    }
                )
                async for message in websocket:
                    if message.type != aiohttp.WSMsgType.TEXT:
                        continue
                    payload = message.json()
                    if payload.get("id") != 1:
                        continue
                    result = payload.get("result", {})
                    if "exceptionDetails" in result:
                        raise RuntimeError("CDP JavaScript exception")
                    return result.get("result", {}).get("value")
        raise RuntimeError("CDP response missing")

    async def probe(self, target: dict) -> FrontendState:
        value = await asyncio.wait_for(
            self._evaluate(target, _PROBE_SCRIPT, False),
            timeout=self._timeout_s,
        )
        if not isinstance(value, dict):
            raise ValueError("invalid CDP probe response")
        return FrontendState(**value)

    async def recover(self, target: dict, script: str) -> dict:
        value = await asyncio.wait_for(
            self._evaluate(target, script, True),
            timeout=self._timeout_s,
        )
        if not isinstance(value, dict):
            raise ValueError("invalid CDP recovery response")
        return value


async def recover_frontend(
    decky_version: str,
    *,
    transport_factory: Callable[[], object] | None = None,
    probe_attempts: int = 24,
    probe_interval_s: float = 0.25,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> RecoveryResult:
    if not is_affected_version(decky_version):
        return RecoveryResult("skipped_version")

    sleeper = sleep or asyncio.sleep
    attempted = False
    try:
        transport = (transport_factory or LocalCdpTransport)()
        targets = [
            target
            for target in await transport.list_targets()
            if _is_shared_target(target)
        ]
        if len(targets) != 1:
            return RecoveryResult("ambiguous_target")

        target = targets[0]
        previous = None
        for attempt in range(max(1, int(probe_attempts))):
            state = await transport.probe(target)
            status = _state_status(state)
            if status not in {"waiting", "recoverable"}:
                return RecoveryResult(status)
            if status == "recoverable" and state == previous:
                attempted = True
                outcome = await transport.recover(target, build_recovery_script())
                recovered = (
                    outcome.get("status") == "recovered"
                    and outcome.get("decky_backend") is True
                    and outcome.get("decky_plugin_loader") is True
                )
                if recovered:
                    return RecoveryResult("recovered", attempted=True)
                return RecoveryResult(
                    str(outcome.get("status") or "postcondition_failed"),
                    attempted=True,
                    detail=str(outcome.get("detail") or "") or None,
                )
            previous = state if status == "recoverable" else None
            if attempt + 1 < probe_attempts:
                await sleeper(max(0.0, float(probe_interval_s)))
        return RecoveryResult("observation_timeout")
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001
        return RecoveryResult(
            "transport_error",
            attempted=attempted,
            detail=type(error).__name__,
        )
