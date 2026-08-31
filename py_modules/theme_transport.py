from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import ssl
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import (
    HTTPSHandler,
    HTTPRedirectHandler,
    OpenerDirector,
    ProxyHandler,
    Request,
    build_opener,
)

from theme_remote_contract import normalize_pages_base_url


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 3
_MAX_METADATA_BYTES = 64 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_SHA256 = frozenset("0123456789abcdef")
_CHUNK_BYTES = 64 * 1024
_CATALOG_PATH = "themes/v1/catalog.json"


class ThemeTransportError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DownloadReceipt:
    path: Path
    size: int
    sha256: str


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _default_opener() -> OpenerDirector:
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return build_opener(
        ProxyHandler({}),
        HTTPSHandler(context=context),
        _NoRedirectHandler(),
    )


def _header(response: Any, name: str) -> str | None:
    value = response.headers.get(name)
    if value is not None:
        return str(value)
    lower_name = name.lower()
    for key, child in response.headers.items():
        if str(key).lower() == lower_name:
            return str(child)
    return None


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class ThemeHttpTransport:
    def __init__(
        self,
        pages_base_url: str,
        *,
        opener: Any | None = None,
        clock: Any = time.monotonic,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        operation_timeout: float = 30.0,
    ):
        self.pages_base_url = normalize_pages_base_url(pages_base_url)
        self._base = urlsplit(self.pages_base_url)
        try:
            ipaddress.ip_address(self._base.hostname or "")
        except ValueError:
            pass
        else:
            raise ThemeTransportError("channel_disabled", "Pages origin cannot be an IP address")
        if connect_timeout <= 0 or read_timeout <= 0 or operation_timeout <= 0:
            raise ValueError("Theme transport timeouts must be positive")
        self._prefix = f"{self._base.path.rstrip('/')}/themes/v1/"
        self._opener = opener if opener is not None else _default_opener()
        self._clock = clock
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._operation_timeout = operation_timeout

    def _resolve(self, relative_path: str) -> str:
        if (
            not isinstance(relative_path, str)
            or not relative_path
            or relative_path.startswith(("/", "//"))
            or "?" in relative_path
            or "#" in relative_path
        ):
            raise ThemeTransportError("redirect_rejected", "Theme path is invalid")
        decoded = unquote(relative_path)
        if any(part in ("", ".", "..") for part in decoded.split("/")):
            raise ThemeTransportError("redirect_rejected", "Theme path is invalid")
        target = urljoin(f"{self.pages_base_url}/", relative_path)
        self._validate_target(target)
        return target

    def _validate_target(self, value: str) -> None:
        try:
            target = urlsplit(value)
            target_port = target.port
        except ValueError as error:
            raise ThemeTransportError("redirect_rejected", "Theme URL is invalid") from error
        if (
            target.scheme != "https"
            or target.hostname != self._base.hostname
            or target_port not in (None, 443)
            or target.username is not None
            or target.password is not None
            or target.fragment
            or not target.path.startswith(self._prefix)
            or any(part in (".", "..") for part in unquote(target.path).split("/"))
        ):
            raise ThemeTransportError(
                "redirect_rejected", "Theme redirect escaped the registered Pages prefix"
            )

    def _deadline(self) -> float:
        return float(self._clock()) + self._operation_timeout

    def _check_deadline(self, deadline: float) -> None:
        if float(self._clock()) > deadline:
            raise ThemeTransportError("timeout", "Theme request exceeded its deadline")

    def _map_failure(self, error: BaseException) -> ThemeTransportError:
        if isinstance(error, ThemeTransportError):
            return error
        if isinstance(error, ssl.SSLError):
            return ThemeTransportError("tls_error", "Theme TLS verification failed")
        if isinstance(error, (TimeoutError, socket.timeout)):
            return ThemeTransportError("timeout", "Theme request timed out")
        if isinstance(error, URLError):
            reason = error.reason
            if isinstance(reason, ssl.SSLError):
                return ThemeTransportError("tls_error", "Theme TLS verification failed")
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return ThemeTransportError("timeout", "Theme request timed out")
            return ThemeTransportError("offline", "Theme service is unavailable")
        if isinstance(error, OSError):
            return ThemeTransportError("offline", "Theme service is unavailable")
        return ThemeTransportError("offline", "Theme service is unavailable")

    def _set_read_timeout(self, response: Any) -> None:
        setter = getattr(response, "set_read_timeout", None)
        if callable(setter):
            setter(self._read_timeout)
            return
        try:
            response.fp.raw._sock.settimeout(self._read_timeout)
        except (AttributeError, OSError):
            return

    def _open_final(self, relative_path: str, accept: str, deadline: float) -> Any:
        target = self._resolve(relative_path)
        for redirects in range(_MAX_REDIRECTS + 1):
            self._check_deadline(deadline)
            request = Request(
                target,
                headers={
                    "Accept": accept,
                    "Accept-Encoding": "identity",
                    "Cache-Control": "no-cache",
                    "User-Agent": "Panel-de-Control-theme-client/1",
                },
                method="GET",
            )
            try:
                response = self._opener.open(request, timeout=self._connect_timeout)
            except HTTPError as error:
                response = error
            except BaseException as error:
                raise self._map_failure(error) from error
            status = int(getattr(response, "status", getattr(response, "code", 0)))
            if status in _REDIRECT_STATUSES:
                location = _header(response, "Location")
                response.close()
                if redirects >= _MAX_REDIRECTS or not location:
                    raise ThemeTransportError(
                        "redirect_rejected", "Theme redirect limit was exceeded"
                    )
                target = urljoin(target, location)
                self._validate_target(target)
                continue
            if status == 429:
                response.close()
                raise ThemeTransportError("rate_limited", "Theme service rate limit was reached")
            if status != 200:
                response.close()
                raise ThemeTransportError("http_status", "Theme service returned an invalid status")
            self._set_read_timeout(response)
            return response
        raise ThemeTransportError("redirect_rejected", "Theme redirect limit was exceeded")

    def _content_length(self, response: Any, maximum: int, code: str) -> int:
        raw = _header(response, "Content-Length")
        try:
            length = int(raw or "")
        except ValueError as error:
            raise ThemeTransportError(code, "Theme response length is invalid") from error
        if length <= 0 or length > maximum:
            raise ThemeTransportError(code, "Theme response length is invalid")
        return length

    @staticmethod
    def _require_mime(response: Any, expected: str, code: str) -> None:
        content_type = (_header(response, "Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != expected:
            raise ThemeTransportError(code, "Theme response type is invalid")

    def fetch_metadata(self, relative_path: str) -> bytes:
        deadline = self._deadline()
        response = self._open_final(relative_path, "application/json", deadline)
        try:
            self._require_mime(response, "application/json", "invalid_descriptor")
            expected = self._content_length(
                response, _MAX_METADATA_BYTES, "descriptor_too_large"
            )
            blocks: list[bytes] = []
            total = 0
            while True:
                self._check_deadline(deadline)
                try:
                    block = response.read(min(_CHUNK_BYTES, expected - total + 1))
                except BaseException as error:
                    raise self._map_failure(error) from error
                if not block:
                    break
                total += len(block)
                if total > expected or total > _MAX_METADATA_BYTES:
                    raise ThemeTransportError(
                        "descriptor_too_large", "Theme metadata exceeds its size limit"
                    )
                blocks.append(block)
            if total != expected:
                raise ThemeTransportError(
                    "size_mismatch", "Theme metadata size does not match its response"
                )
            return b"".join(blocks)
        finally:
            response.close()

    def fetch_catalog(self) -> bytes:
        return self.fetch_metadata(_CATALOG_PATH)

    def download_artifact(
        self,
        relative_path: str,
        destination: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> DownloadReceipt:
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size <= 0
            or expected_size > _MAX_ARTIFACT_BYTES
        ):
            raise ThemeTransportError("artifact_too_large", "Theme artifact size is invalid")
        if (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(character not in _SHA256 for character in expected_sha256)
        ):
            raise ThemeTransportError("hash_mismatch", "Theme artifact digest is invalid")
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = self._deadline()
        response = self._open_final(relative_path, "application/zip", deadline)
        temporary: Path | None = None
        try:
            self._require_mime(response, "application/zip", "invalid_archive")
            declared_size = self._content_length(
                response, _MAX_ARTIFACT_BYTES, "artifact_too_large"
            )
            if declared_size != expected_size:
                raise ThemeTransportError(
                    "size_mismatch", "Theme artifact size does not match its descriptor"
                )
            digest = hashlib.sha256()
            total = 0
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination_path.name}.",
                suffix=".part",
                dir=destination_path.parent,
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                while True:
                    self._check_deadline(deadline)
                    try:
                        block = response.read(min(_CHUNK_BYTES, expected_size - total + 1))
                    except BaseException as error:
                        raise self._map_failure(error) from error
                    if not block:
                        break
                    total += len(block)
                    if total > expected_size or total > _MAX_ARTIFACT_BYTES:
                        raise ThemeTransportError(
                            "size_mismatch", "Theme artifact exceeds its declared size"
                        )
                    stream.write(block)
                    digest.update(block)
                stream.flush()
                os.fsync(stream.fileno())
            if total != expected_size:
                raise ThemeTransportError(
                    "size_mismatch", "Theme artifact size does not match its descriptor"
                )
            actual_digest = digest.hexdigest()
            if actual_digest != expected_sha256:
                raise ThemeTransportError(
                    "hash_mismatch", "Theme artifact hash does not match its descriptor"
                )
            os.replace(temporary, destination_path)
            temporary = None
            _fsync_directory(destination_path.parent)
            return DownloadReceipt(
                path=destination_path,
                size=total,
                sha256=actual_digest,
            )
        finally:
            response.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
