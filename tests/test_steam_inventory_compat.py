"""Inventory isolation, lease cleanup and worker failure containment."""
import asyncio
import importlib.util
import json
import subprocess
import sys
import types

import pytest


def module():
    assert importlib.util.find_spec("steam_inventory_compat"), "inventory worker missing"
    import steam_inventory_compat
    return steam_inventory_compat


@pytest.mark.parametrize("url,allowed", [
    ("https://steamcommunity.com/my/inventory", True),
    ("https://steamcommunity.com/profiles/7656119/inventory/#440", True),
    ("https://steamcommunity.com/id/name/inventory?l=spanish", True),
    ("https://steamcommunity.com/my/inventory/extra", False),
    ("https://steamcommunity.com:443/my/inventory", False),
    ("https://user@steamcommunity.com/my/inventory", False),
    ("http://steamcommunity.com/my/inventory", False),
    ("https://steamcommunity.com.evil/my/inventory", False),
    ("https://steamcommunity.com/id/a%2fb/inventory", False),
    ("https://steamcommunity.com/market", False),
])
def test_inventory_url_boundary(url, allowed):
    assert module().inventory_url(url) is allowed


@pytest.mark.parametrize("url,allowed", [
    ("ws://127.0.0.1:8080/devtools/page/ABCD", True),
    ("ws://127.0.0.1:8081/devtools/page/ABCD", True),
    ("ws://localhost:8080/devtools/page/ABCD", False),
    ("ws://127.0.0.1:9000/devtools/page/ABCD", False),
    ("ws://127.0.0.1:8080/devtools/browser/ABCD", False),
    ("ws://user@127.0.0.1:8080/devtools/page/ABCD", False),
    ("ws://127.0.0.1:8080/devtools/page/ABCD?x=1", False),
])
def test_debugger_endpoint_boundary(url, allowed):
    assert module().debugger_url(url) is allowed


def test_page_guard_renewal_and_expiry_preserve_other_styles():
    mod = module()
    # Execute the shipped script, including the navigation-time guard and lease.
    harness = r"""
    const vm = require('node:vm');
    const scripts = JSON.parse(process.argv[1]);
    let clock = 0, timer = null;
    const styles = new Map([['foreign-style', {id: 'foreign-style'}]]);
    const document = {
      documentElement: {classList: {contains: () => true}},
      body: {classList: {contains: () => true}},
      head: {appendChild: e => styles.set(e.id, e)},
      getElementById: id => styles.get(id) || null,
      createElement: () => ({remove() {styles.delete(this.id)}}),
      addEventListener() {}, removeEventListener() {},
    };
    const context = {document, URL, location: {href: 'https://steamcommunity.com/my/inventory'},
      Date: {now: () => clock}, setTimeout: fn => {timer = fn; return 1},
      clearTimeout: () => {timer = null}};
    context.window = context;
    vm.createContext(context);
    const run = s => vm.runInContext(s, context);
    const out = [];
    out.push(run(scripts.apply)); out.push(styles.size);
    clock = 3000; out.push(run(scripts.apply)); out.push(styles.size);
    clock = 20000; timer(); out.push(styles.size);
    context.location.href = 'https://evil.example/my/inventory';
    out.push(run(scripts.apply)); out.push(styles.size);
    context.location.href = 'https://steamcommunity.com/my/inventory';
    run(scripts.apply); out.push(run(scripts.remove)); out.push(styles.size);
    context.location.href += '\n'; out.push(run(scripts.apply)); out.push(styles.size);
    context.location.href = 'https://steamcommunity.com/my/inventory';
    document.documentElement.classList.contains = () => false;
    out.push(run(scripts.apply)); out.push(styles.size);
    document.documentElement.classList.contains = () => true;
    run(scripts.apply); const staleTimer = timer;
    run(scripts.newApply);
    out.push(run(scripts.remove)); out.push(styles.size);
    clock = 999999; staleTimer(); out.push(styles.size);
    out.push(run(scripts.newRemove)); out.push(styles.size);
    console.log(JSON.stringify(out));
    """
    newer = mod.SteamInventoryCompat()
    result = subprocess.run(
        ["node", "-e", harness, json.dumps({"apply": mod.APPLY_SCRIPT, "remove": mod.REMOVE_SCRIPT,
                                          "newApply": newer._apply_script,
                                          "newRemove": newer._remove_script})],
        capture_output=True, text=True, timeout=5, check=True,
    )
    assert json.loads(result.stdout) == ["applied", 2, "applied", 2, 1, "skipped", 1, "removed", 1,
                                       "skipped", 1, "skipped", 1, "superseded", 2, 2, "removed", 1]


def test_focused_inventory_control_scrolls_after_layout_and_releases_resources():
    mod = module()
    newer = mod.SteamInventoryCompat()
    harness = r"""
    const vm = require('node:vm'), assert = require('node:assert/strict');
    const scripts = JSON.parse(process.argv[1]);
    const styles = new Map(), listeners = new Map(), frames = new Map(), observers = new Set();
    let serial = 0, clock = 0, lease;
    let bottom = 560, scrolled = 0, viewportBottom = 446;
    const popup = {firstElementChild: {}, getBoundingClientRect: () => ({top: 24, bottom: viewportBottom, left: 0, right: 800})};
    const active = {closest: selector => {
      assert.equal(selector, 'dialog.economy_modal_ctn .economy_item_popup_scroll'); return popup;
    }, getBoundingClientRect: () => ({top: bottom - 24, bottom, left: 10, right: 100}),
      scrollIntoView: options => {assert.deepEqual(JSON.parse(JSON.stringify(options)), {block:'nearest',inline:'nearest'}); scrolled++; bottom = 400},
      focus() {throw Error('must preserve focus')} };
    const document = {activeElement: active,
      documentElement: {classList: {contains: () => true}}, body: {classList: {contains: () => true}},
      head: {appendChild: e => styles.set(e.id,e)}, getElementById: id => styles.get(id) || null,
      createElement: () => ({remove() {styles.delete(this.id)}}),
      addEventListener: (name, fn) => {if (!listeners.has(name)) listeners.set(name,new Set()); listeners.get(name).add(fn)},
      removeEventListener: (name, fn) => listeners.get(name)?.delete(fn)};
    const context = {document, location: {href:'https://steamcommunity.com/my/inventory'},
      Date: {now: () => clock}, setTimeout: fn => {lease=fn; return 1}, clearTimeout() {},
      requestAnimationFrame: fn => {frames.set(++serial,fn); return serial},
      cancelAnimationFrame: id => frames.delete(id),
      ResizeObserver: class {constructor(fn) {this.fn=fn; this.targets=new Set()} observe(target) {assert.ok(target===popup || target===popup.firstElementChild); this.targets.add(target); observers.add(this)} disconnect() {this.targets.clear(); observers.delete(this)}}};
    context.window=context; vm.createContext(context);
    const run = s => vm.runInContext(s,context);
    const tick = () => {const pending=[...frames.values()]; frames.clear(); pending.forEach(fn=>fn())};
    const focus = () => [...(listeners.get('focusin')||[])].forEach(fn=>fn());
    run(scripts.apply); assert.equal(scrolled,0); tick(); assert.equal(scrolled,0); tick();
    assert.equal(scrolled,1); assert.equal(document.activeElement,active); assert.equal(observers.size,1);
    bottom=650; run(scripts.apply); tick(); tick(); assert.equal(scrolled,1);
    bottom=600; [...observers].forEach(o=>o.fn()); tick(); tick(); assert.equal(scrolled,2);
    focus(); focus(); assert.equal(frames.size,1); tick(); tick(); assert.equal(scrolled,2);
    document.activeElement={closest:()=>null}; focus(); assert.equal(observers.size,0);
    tick(); tick(); assert.equal(scrolled,2);
    document.activeElement=active; focus(); tick(); tick();
    viewportBottom=350;
    [...observers].filter(o=>o.targets.has(popup)).forEach(o=>o.fn());
    tick(); tick(); assert.equal(scrolled,3);
    viewportBottom=446;
    document.activeElement=active; bottom=700; focus(); assert.equal(frames.size,1);
    run(scripts.newApply); assert.equal(listeners.get('focusin').size,1); assert.equal(frames.size,1);
    run(scripts.remove); assert.equal(listeners.get('focusin').size,1);
    run(scripts.newRemove); assert.equal(listeners.get('focusin').size,0); assert.equal(frames.size,0); assert.equal(observers.size,0);
    run(scripts.apply); clock=20000; lease();
    assert.equal(listeners.get('focusin').size,0); assert.equal(frames.size,0); assert.equal(observers.size,0);
    console.log('ok');
    """
    result = subprocess.run(["node", "-e", harness, json.dumps({
        "apply": mod.APPLY_SCRIPT, "remove": mod.REMOVE_SCRIPT,
        "newApply": newer._apply_script, "newRemove": newer._remove_script,
    })], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_missing_transport_fails_open(monkeypatch):
    mod = module()
    monkeypatch.setitem(sys.modules, "aiohttp", None)

    async def run():
        worker = mod.SteamInventoryCompat()
        worker.start()
        await asyncio.sleep(0)
        assert worker.state()["status"] == "unavailable"
        await worker.stop()
        assert worker.state()["status"] == "stopped"
    asyncio.run(run())


def test_scan_handles_chunked_discovery_and_never_connects_other_targets():
    mod = module()
    endpoint = "ws://127.0.0.1:8080/devtools/page/A"
    permitted = {endpoint}
    attached = []
    targets = [
        {"type": "page", "url": "https://steamcommunity.com/my/inventory", "webSocketDebuggerUrl": endpoint},
        {"type": "page", "url": "https://evil.example/my/inventory",
         "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/B"},
        {"type": "page", "url": "https://steamcommunity.com/my/inventory",
         "webSocketDebuggerUrl": "ws://evil.example:8080/devtools/page/C"},
    ]

    class Response:
        def __init__(self):
            self.content = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        async def iter_chunked(self, n):
            data = json.dumps(targets).encode()
            yield data[:12]
            yield data[12:]

    class Socket(Response):
        async def send_json(self, payload):
            assert payload["method"] == "Runtime.evaluate"
            self.removing = payload["params"]["expression"] == worker._remove_script

        async def receive_json(self):
            return {"id": 1, "result": {"result": {"value": "removed" if self.removing else "applied"}}}

    class Session:
        def get(self, url, **kw):
            assert url == "http://127.0.0.1:8080/json/list" and kw["allow_redirects"] is False
            return Response()

        def ws_connect(self, url, **kw):
            assert url in permitted, "must not attach to unrelated or remote targets"
            attached.append(url)
            return Socket()

    async def run():
        await worker._scan(Session())
        assert worker.state()["applied_targets"] == 1
        targets[0]["url"] = "https://steamcommunity.com/market"
        await worker._scan(Session())
        assert worker.state()["applied_targets"] == 0
        assert not worker._owned
        targets.clear()
        for i in range(20):
            address = f"ws://127.0.0.1:8080/devtools/page/P{i}"
            permitted.add(address)
            targets.append({"type": "page", "url": "https://steamcommunity.com/my/inventory",
                            "webSocketDebuggerUrl": address})
        attached.clear()
        await worker._scan(Session())
        assert 0 < len(attached) <= 8
        targets.reverse()
        attached.clear()
        await worker._scan(Session())
        assert 0 < len(attached) <= 8
    worker = mod.SteamInventoryCompat()
    asyncio.run(run())


def test_stop_reports_unconfirmed_removal_and_does_not_keep_session(monkeypatch):
    mod = module()
    closed = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            closed.append(True)

    async def run():
        worker = mod.SteamInventoryCompat()
        worker._http = types.SimpleNamespace(ClientSession=lambda **kw: Session())
        worker._owned.add("ws://127.0.0.1:8080/devtools/page/A")

        async def evaluate(*args):
            raise OSError("a private URL")

        monkeypatch.setattr(worker, "_evaluate", evaluate)
        await worker.stop()
        assert closed == [True]
        assert worker.state()["cleanup_pending"] == 1
        assert worker.state()["error_type"] == "lease_cleanup_pending"
        assert "private" not in json.dumps(worker.state())
    asyncio.run(run())


def test_worker_reconnects_and_stop_cancels_inflight(monkeypatch):
    mod = module()
    monkeypatch.setattr(mod, "POLL_SECONDS", 0.001)
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setitem(sys.modules, "aiohttp", types.SimpleNamespace(ClientSession=lambda **kw: Session()))

    async def run():
        worker = mod.SteamInventoryCompat()
        entered = asyncio.Event()
        attempts = 0

        async def scan(session):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("private inventory url must not enter diagnostics")
            entered.set()
            await asyncio.Future()

        monkeypatch.setattr(worker, "_scan", scan)
        worker.start()
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(worker.stop(), 1)
        assert attempts == 2
        assert worker.state()["status"] == "stopped"
        assert "private" not in json.dumps(worker.state())
        assert worker._task is None
    asyncio.run(run())
