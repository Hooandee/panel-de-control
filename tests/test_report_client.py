import json
import os

from report.client import parse_response, save_local


def test_parse_response_success():
    body = json.dumps({"ok": True, "code": "PDC-7QK2", "issueUrl": "u"}).encode()
    out = parse_response(200, body)
    assert out == {"ok": True, "code": "PDC-7QK2", "issue_url": "u"}


def test_parse_response_2xx_without_code_is_failure():
    # a 200 with no code is not a success.
    out = parse_response(200, json.dumps({"ok": True}).encode())
    assert out["ok"] is False


def test_parse_response_http_error_surfaces_message():
    out = parse_response(429, json.dumps({"error": "rate limited"}).encode())
    assert out == {"ok": False, "error": "rate limited"}


def test_parse_response_garbage_body():
    out = parse_response(500, b"<html>oops")
    assert out["ok"] is False
    assert "500" in out["error"]


def test_save_local_writes_json(tmp_path):
    path = save_local(str(tmp_path), {"a": 1}, code="PDC-XX")
    assert path and path.endswith("report-PDC-XX.json")
    with open(path) as f:
        assert json.load(f) == {"a": 1}


def test_save_local_offline_name(tmp_path):
    path = save_local(str(tmp_path), {"a": 1})
    assert os.path.basename(path) == "report-offline.json"
