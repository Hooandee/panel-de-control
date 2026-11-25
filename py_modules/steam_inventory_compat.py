"""Bounded, inventory-only Steam browser compatibility; no public injection API."""
import asyncio
import json
import re
import secrets

POLL_SECONDS = 3.0
REQUEST_SECONDS = 3.0
MAX_TARGETS = 8
STYLE_ID = "pdc-steam-inventory-dialog-compat"
_OWNER = "__pdcSteamInventoryCompat"
_INVENTORY = r"https://steamcommunity\.com/(?:my|profiles/[0-9]+|id/[A-Za-z0-9_-]+)/inventory/?(?:[?#][^\s]*)?"
_DEBUGGER = r"ws://127\.0\.0\.1:808[01]/devtools/page/[A-Za-z0-9_-]+"
_CSS = (
    "html.GamepadMode body.inventory_page dialog.economy_modal_ctn"
    "{top:50%!important;transform:translateY(-50%);margin-block:0}"
    "html.GamepadMode body.inventory_page dialog.economy_modal_ctn .economy_item_popup_scroll"
    "{max-height:calc(100vh - 48px);overflow-y:auto}"
)


def inventory_url(value):
    return isinstance(value, str) and re.fullmatch(_INVENTORY, value, re.ASCII) is not None


def debugger_url(value):
    return isinstance(value, str) and re.fullmatch(_DEBUGGER, value, re.ASCII) is not None


REMOVE_SCRIPT = """(() => {
    const key = %s, id = %s, generation = '__PDC_INVENTORY_GENERATION__';
    const owner = window[key];
    if (owner && owner.generation !== generation) return 'superseded';
    owner?.dispose?.();
    if (owner) clearTimeout(owner.timer);
    document.getElementById(id)?.remove();
    delete window[key];
    return document.getElementById(id) === null ? 'removed' : 'unverifiable';
})()""" % (json.dumps(_OWNER), json.dumps(STYLE_ID))

APPLY_SCRIPT = """(() => {
    const key = %s, id = %s, generation = '__PDC_INVENTORY_GENERATION__';
    const eligible = () => new RegExp(%s).test(location.href)
        && document.documentElement?.classList.contains('GamepadMode')
        && document.body?.classList.contains('inventory_page');
    const remove = () => {
        const owner = window[key];
        owner?.dispose?.();
        if (owner) clearTimeout(owner.timer);
        document.getElementById(id)?.remove();
        delete window[key];
    };
    if (!eligible() || !document.head) { remove(); return 'skipped'; }
    let style = document.getElementById(id);
    if (!style) {
        style = document.createElement('style');
        style.id = id;
        document.head.appendChild(style);
    }
    const css = %s;
    if (style.textContent !== css) style.textContent = css;
    const previous = window[key];
    if (previous) clearTimeout(previous.timer);
    if (previous && previous.generation !== generation) previous.dispose?.();
    const owner = previous?.generation === generation ? previous : {generation};
    const fresh = owner !== previous;
    owner.expires = Date.now() + 12000;
    const check = () => {
        if (window[key] !== owner) return;
        if (!eligible() || Date.now() >= owner.expires) { remove(); return; }
        owner.timer = setTimeout(check, 1000);
    };
    window[key] = owner;
    if (fresh) {
        owner.frame = null;
        owner.observed = null;
        const popupFor = active => active?.closest?.('dialog.economy_modal_ctn .economy_item_popup_scroll');
        owner.align = () => {
            if (window[key] !== owner || !eligible()) return;
            const popup = popupFor(document.activeElement);
            const content = popup?.firstElementChild || null;
            if (content !== owner.observed) {
                owner.observer?.disconnect();
                owner.observed = content;
                if (content && typeof ResizeObserver === 'function') {
                    owner.observer ||= new ResizeObserver(owner.align);
                    owner.observer.observe(popup);
                    owner.observer.observe(content);
                }
            }
            if (!popup) {
                if (owner.frame !== null) cancelAnimationFrame(owner.frame);
                owner.frame = null;
                return;
            }
            if (owner.frame !== null) return;
            owner.frame = requestAnimationFrame(() => {
                owner.frame = requestAnimationFrame(() => {
                    owner.frame = null;
                    if (window[key] !== owner || !eligible()) return;
                    const active = document.activeElement;
                    const current = popupFor(active);
                    if (!current) return;
                    const rect = active.getBoundingClientRect();
                    const bounds = current.getBoundingClientRect();
                    if (rect.top < bounds.top || rect.bottom > bounds.bottom
                        || rect.left < bounds.left || rect.right > bounds.right) {
                        active.scrollIntoView({block: 'nearest', inline: 'nearest'});
                    }
                });
            });
        };
        owner.dispose = () => {
            document.removeEventListener('focusin', owner.align, true);
            owner.observer?.disconnect();
            if (owner.frame !== null) cancelAnimationFrame(owner.frame);
            owner.frame = null;
            owner.observed = null;
        };
        document.addEventListener('focusin', owner.align, true);
        owner.align();
    }
    owner.timer = setTimeout(check, 1000);
    return document.getElementById(id)?.textContent === %s ? 'applied' : 'unverifiable';
})()""" % (json.dumps(_OWNER), json.dumps(STYLE_ID), json.dumps("^" + _INVENTORY + "$"),
          json.dumps(_CSS), json.dumps(_CSS))


class SteamInventoryCompat:
    def __init__(self, journal=None):
        generation = secrets.token_hex(16)
        self._apply_script = APPLY_SCRIPT.replace('__PDC_INVENTORY_GENERATION__', generation)
        self._remove_script = REMOVE_SCRIPT.replace('__PDC_INVENTORY_GENERATION__', generation)
        self._journal = journal
        self._task = None
        self._http = None
        self._owned = set()
        self._stopping = False
        self._state = {"status": "idle", "applied_targets": 0,
                       "cleanup_pending": 0, "error_type": None}

    def state(self):
        return dict(self._state)

    def _publish(self, status, *, applied=0, error=None):
        state = {"status": status, "applied_targets": applied,
                 "cleanup_pending": len(self._owned) if self._stopping else 0,
                 "error_type": error}
        if state != self._state:
            self._state = state
            if self._journal:
                try:
                    self._journal(dict(state))
                except Exception:
                    pass

    def start(self):
        if not self._stopping and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        try:
            import aiohttp
        except ImportError:
            self._publish("unavailable", error="transport_missing")
            return
        self._http = aiohttp
        try:
            async with aiohttp.ClientSession(trust_env=False) as session:
                while True:
                    try:
                        await self._scan(session)
                    except Exception as exc:
                        self._publish("unavailable", error=type(exc).__name__)
                    await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._publish("unavailable", error=type(exc).__name__)

    async def _evaluate(self, session, endpoint, script):
        # Never connect to a returned arbitrary host, port or browser target.
        if not debugger_url(endpoint):
            raise ValueError("invalid_debugger_endpoint")
        async with asyncio.timeout(REQUEST_SECONDS):
            async with session.ws_connect(endpoint, max_msg_size=65536) as ws:
                await ws.send_json({"id": 1, "method": "Runtime.evaluate", "params": {
                    "expression": script, "returnByValue": True,
                }})
                for _ in range(32):
                    message = await ws.receive_json()
                    if message.get("id") == 1:
                        result = message.get("result", {})
                        if "error" in message or "exceptionDetails" in result:
                            raise RuntimeError("evaluation_failed")
                        return result.get("result", {}).get("value")
                raise RuntimeError("evaluation_unverifiable")

    async def _scan(self, session):
        async with asyncio.timeout(REQUEST_SECONDS):
            async with session.get("http://127.0.0.1:8080/json/list", allow_redirects=False) as response:
                response.raise_for_status()
                # Bound bytes before decoding: discovery contains other private tabs.
                raw = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    raw.extend(chunk)
                    if len(raw) > 262144:
                        raise ValueError("target_list_too_large")
                targets = json.loads(raw)
        if not isinstance(targets, list):
            raise ValueError("invalid_target_list")
        eligible = set()
        live = set()
        for target in targets:
            if not isinstance(target, dict):
                continue
            endpoint = target.get("webSocketDebuggerUrl")
            if target.get("type") == "page" and debugger_url(endpoint):
                live.add(endpoint)
                if inventory_url(target.get("url")):
                    eligible.add(endpoint)
        self._owned.intersection_update(live)
        # Retain existing eligible pages; cleanup consumes a slot until confirmed.
        # Discovery reordering must not multiply sockets or abandoned leases.
        eligible = (eligible & self._owned) | set(sorted(eligible - self._owned)[
            :max(0, MAX_TARGETS - len(self._owned))
        ])
        results = await asyncio.gather(*[
            self._update(session, endpoint, endpoint in eligible)
            for endpoint in self._owned | eligible
        ])
        errors = [result for result in results if result not in ("applied", "removed", "skipped")]
        self._publish("degraded" if errors else "active", applied=results.count("applied"),
                      error=errors[0] if errors else None)

    async def _update(self, session, endpoint, apply):
        if apply:
            # A cancelled evaluation may already have inserted the style.
            self._owned.add(endpoint)
        try:
            result = await self._evaluate(session, endpoint, self._apply_script if apply else self._remove_script)
            if result in ("removed", "skipped", "superseded"):
                self._owned.discard(endpoint)
            if result == "superseded":
                return "removed"
            if result in ("applied", "removed", "skipped"):
                return result
            return "unverifiable"
        except Exception as exc:
            return type(exc).__name__

    async def stop(self):
        self._stopping = True
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=0.25)
            except (asyncio.CancelledError, TimeoutError):
                pass
        error = None
        if self._owned and self._http:
            try:
                async with asyncio.timeout(0.75):
                    async with self._http.ClientSession(trust_env=False) as session:
                        await asyncio.gather(*[
                            self._update(session, endpoint, False) for endpoint in tuple(self._owned)
                        ])
            except Exception as exc:
                error = type(exc).__name__
        self._publish("stopped", error=error or ("lease_cleanup_pending" if self._owned else None))
