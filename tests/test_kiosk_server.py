import asyncio
import json

import pytest

from kiosk.server import KioskServer, TOKEN_HEADER


async def _request(port, raw: bytes) -> tuple[int, bytes]:
    """One-shot client: asks the server to close after answering and reads to EOF."""
    if b"\r\n" in raw and b"Connection:" not in raw:
        line, rest = raw.split(b"\r\n", 1)
        raw = line + b"\r\nConnection: close\r\n" + rest
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    data = await reader.read()
    writer.close()
    head, _, body = data.partition(b"\r\n\r\n")
    return int(head.split(b" ")[1]), body


def _post(token: str, payload: dict) -> bytes:
    body = json.dumps(payload).encode()
    return (
        f"POST /rpc HTTP/1.1\r\nHost: x\r\n{TOKEN_HEADER}: {token}\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode() + body


@pytest.fixture
def static_dir(tmp_path):
    (tmp_path / "index.html").write_text("<p>kiosk</p>")
    (tmp_path / "kiosk.js").write_text("1")
    (tmp_path / "secret.txt").write_text("nope")
    return tmp_path


def _serve(static_dir, dispatch=None, allowed=("get_tdp_state",), errors=None):
    async def default(name, args):
        return {"method": name, "args": args}

    return KioskServer(
        str(static_dir),
        dispatch or default,
        allowed,
        on_error=(lambda m, e: errors.append((m, e))) if errors is not None else (lambda m, e: None),
    )


def test_serves_only_the_bundle_files(static_dir):
    async def run():
        server = _serve(static_dir)
        await server.start()
        try:
            index = await _request(server.port, b"GET /?k=abc HTTP/1.1\r\n\r\n")
            secret = await _request(server.port, b"GET /secret.txt HTTP/1.1\r\n\r\n")
            escape = await _request(server.port, b"GET /../main.py HTTP/1.1\r\n\r\n")
        finally:
            await server.stop()
        return index, secret, escape

    index, secret, escape = asyncio.run(run())
    assert index == (200, b"<p>kiosk</p>")
    assert secret[0] == 404
    assert escape[0] == 404


def test_rpc_requires_the_launch_token(static_dir):
    async def run():
        server = _serve(static_dir)
        await server.start()
        try:
            wrong = await _request(server.port, _post("guess", {"method": "get_tdp_state", "args": []}))
            accented = await _request(server.port, _post("contraseña", {"method": "get_tdp_state", "args": []}))
            right = await _request(server.port, _post(server.token, {"method": "get_tdp_state", "args": [1]}))
        finally:
            await server.stop()
        return wrong, accented, right

    wrong, accented, right = asyncio.run(run())
    assert wrong[0] == 403
    assert accented[0] == 403
    assert right[0] == 200
    assert json.loads(right[1]) == {"result": {"method": "get_tdp_state", "args": [1]}}


def test_rpc_rejects_methods_decky_does_not_expose(static_dir):
    async def run():
        server = _serve(static_dir)
        await server.start()
        try:
            return await _request(server.port, _post(server.token, {"method": "_main", "args": []}))
        finally:
            await server.stop()

    status, body = asyncio.run(run())
    assert status == 404
    assert json.loads(body) == {"error": "unknown_method"}


def test_rpc_failures_are_reported_not_hidden(static_dir):
    errors = []

    async def boom(name, args):
        raise RuntimeError("sysfs gone")

    async def run():
        server = _serve(static_dir, dispatch=boom, errors=errors)
        await server.start()
        try:
            return await _request(server.port, _post(server.token, {"method": "get_tdp_state", "args": []}))
        finally:
            await server.stop()

    status, body = asyncio.run(run())
    assert status == 500
    assert json.loads(body) == {"error": "RuntimeError"}
    assert errors == [("get_tdp_state", "RuntimeError: sysfs gone")]


def test_rpc_rejects_malformed_and_oversized_bodies(static_dir):
    async def run():
        server = _serve(static_dir)
        await server.start()
        try:
            bad = await _request(server.port, _post(server.token, {"args": []}))
            huge = await _request(
                server.port,
                f"POST /rpc HTTP/1.1\r\n{TOKEN_HEADER}: {server.token}\r\nContent-Length: {1 << 21}\r\n\r\n".encode(),
            )
        finally:
            await server.stop()
        return bad, huge

    bad, huge = asyncio.run(run())
    assert bad[0] == 400
    assert huge[0] == 413


def test_url_carries_port_and_token(static_dir):
    async def run():
        server = _serve(static_dir)
        await server.start()
        url = server.url
        port, token = server.port, server.token
        await server.stop()
        return url, port, token, server.url

    url, port, token, after = asyncio.run(run())
    assert url == f"http://127.0.0.1:{port}/?k={token}"
    assert after is None


def test_serves_only_resolved_game_art(static_dir, tmp_path):
    hero = tmp_path / "hero.jpg"
    hero.write_bytes(b"jpeg")

    async def run():
        server = KioskServer(
            str(static_dir), lambda *_: None, (),
            art=lambda appid, kind: (str(hero), "image/jpeg") if (appid, kind) == ("413150", "hero") else None,
        )
        await server.start()
        try:
            found = await _request(server.port, b"GET /art/413150/hero HTTP/1.1\r\n\r\n")
            missing = await _request(server.port, b"GET /art/413150/logo HTTP/1.1\r\n\r\n")
            nested = await _request(server.port, b"GET /art/413150/hero/x HTTP/1.1\r\n\r\n")
        finally:
            await server.stop()
        return found, missing, nested

    found, missing, nested = asyncio.run(run())
    assert found == (200, b"jpeg")
    assert missing[0] == 404
    assert nested[0] == 404


def test_one_connection_serves_several_requests(static_dir):
    async def run():
        server = _serve(static_dir)
        await server.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            answers = []
            for _ in range(3):
                writer.write(_post(server.token, {"method": "get_tdp_state", "args": []}))
                await writer.drain()
                head = await reader.readuntil(b"\r\n\r\n")
                length = int(next(line for line in head.split(b"\r\n") if line.lower().startswith(b"content-length")).split(b":")[1])
                assert b"Connection: keep-alive" in head
                answers.append(json.loads(await reader.readexactly(length)))
            writer.close()
            return answers
        finally:
            await server.stop()

    answers = asyncio.run(run())
    assert [a["result"]["method"] for a in answers] == ["get_tdp_state"] * 3


def test_stopping_does_not_wait_for_idle_connections(static_dir):
    async def run():
        server = _serve(static_dir)
        await server.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(_post(server.token, {"method": "get_tdp_state", "args": []}))
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        started = asyncio.get_running_loop().time()
        await asyncio.wait_for(server.stop(), 2)
        writer.close()
        return asyncio.get_running_loop().time() - started

    assert asyncio.run(run()) < 1
