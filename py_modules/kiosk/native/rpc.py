import http.client
import json
import threading
import urllib.parse

TOKEN_HEADER = "x-pdc-kiosk"
TIMEOUT_S = 5.0


class RpcError(RuntimeError):
    pass


class PanelRpc:
    def __init__(self, url: str):
        parsed = urllib.parse.urlsplit(url)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or 80
        self._token = urllib.parse.parse_qs(parsed.query).get("k", [""])[0]
        self._lock = threading.Lock()
        self._conn: http.client.HTTPConnection | None = None

    def call(self, method: str, *args):
        body = json.dumps({"method": method, "args": list(args)})
        headers = {"Content-Type": "application/json", TOKEN_HEADER: self._token}
        payload = self._request("POST", "/rpc", body, headers)
        try:
            reply = json.loads(payload)
        except ValueError as error:
            raise RpcError("bad_reply") from error
        if "error" in reply:
            raise RpcError(str(reply["error"]))
        return reply.get("result")

    def fetch(self, path: str) -> bytes | None:
        try:
            return self._request("GET", path, None, {})
        except RpcError:
            return None

    def _request(self, verb: str, path: str, body: str | None, headers: dict) -> bytes:
        with self._lock:
            for attempt in (0, 1):
                if self._conn is None:
                    self._conn = http.client.HTTPConnection(self._host, self._port, timeout=TIMEOUT_S)
                try:
                    self._conn.request(verb, path, body, headers)
                    response = self._conn.getresponse()
                    payload = response.read()
                except (OSError, http.client.HTTPException) as error:
                    self._conn.close()
                    self._conn = None
                    if attempt:
                        raise RpcError(type(error).__name__) from error
                    continue
                if response.status != 200:
                    raise RpcError(f"http_{response.status}")
                return payload
        raise RpcError("unreachable")
