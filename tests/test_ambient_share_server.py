import json
import time
import urllib.error
import urllib.request

import pytest

from ambient.adapters.share_server import ShareServer, extract_links


def _post(url, payload):
    data = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read())


@pytest.fixture
def server():
    s = ShareServer(host="127.0.0.1", lan_address=lambda: "127.0.0.1")
    yield s
    s.stop()


def test_links_are_pulled_out_of_any_text():
    text = """Mira esto https://www.youtube.com/watch?v=abc123&list=PL1
    twitch.tv/somechannel
    javascript:alert(1)
    ftp://nope.test/a  y también http://radio.test:8000/stream.mp3, gracias"""
    assert extract_links(text) == [
        "https://www.youtube.com/watch?v=abc123&list=PL1",
        "https://twitch.tv/somechannel",
        "http://radio.test:8000/stream.mp3",
    ]
    assert extract_links("x" * 10) == []
    assert len(extract_links("\n".join(f"https://a.test/{i}" for i in range(80)))) == 50


def test_phone_page_and_links_reach_the_queue_only_with_the_token(server):
    session = server.start({"title": "Enviar a Panel"})
    assert session["url"].startswith("http://127.0.0.1:")
    with urllib.request.urlopen(session["url"], timeout=3) as response:
        page = response.read().decode()
    assert "Enviar a Panel" in page
    assert _post(session["url"] + "add", {"text": "https://a.test/1 https://a.test/2"}) == {"added": 2, "links": ["https://a.test/1", "https://a.test/2"]}
    assert server.take() == ["https://a.test/1", "https://a.test/2"]
    assert server.take() == []
    wrong = session["url"].replace(server.token, "x" * len(server.token))
    with pytest.raises(urllib.error.HTTPError) as error:
        _post(wrong + "add", {"text": "https://a.test/3"})
    assert error.value.code == 403
    assert server.take() == []


def test_oversized_or_broken_bodies_are_refused(server):
    session = server.start({})
    with pytest.raises(urllib.error.HTTPError) as error:
        _post(session["url"] + "add", b"{" * 70000)
    assert error.value.code == 413
    with pytest.raises(urllib.error.HTTPError) as error:
        _post(session["url"] + "add", b"not json")
    assert error.value.code == 400


def test_a_session_ends_on_its_own(server):
    session = ShareServer(host="127.0.0.1", lan_address=lambda: "127.0.0.1", ttl_sec=0.3)
    try:
        info = session.start({})
        time.sleep(0.8)
        assert session.active is False
        with pytest.raises(OSError):
            urllib.request.urlopen(info["url"], timeout=1)
    finally:
        session.stop()


def test_without_a_network_there_is_no_session():
    s = ShareServer(host="127.0.0.1", lan_address=lambda: None)
    assert s.start({}) == {"error": "no_network"}
    assert s.active is False
