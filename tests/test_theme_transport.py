from __future__ import annotations

import hashlib
import ssl
from pathlib import Path
from urllib.error import URLError

import pytest

from theme_transport import ThemeHttpTransport, ThemeTransportError


PAGES_BASE = "https://example.invalid/panel-de-control"


class FakeResponse:
    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        content_type: str = "application/json",
        content_length: int | None = None,
        location: str | None = None,
        read_error: Exception | None = None,
    ):
        self.status = status
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(body) if content_length is None else content_length),
        }
        if location is not None:
            self.headers["Location"] = location
        self._body = body
        self._offset = 0
        self._read_error = read_error
        self.read_timeout: float | None = None

    def read(self, size: int) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        block = self._body[self._offset : self._offset + min(size, 7)]
        self._offset += len(block)
        return block

    def close(self) -> None:
        return None

    def set_read_timeout(self, timeout: float) -> None:
        self.read_timeout = timeout


class FakeOpener:
    def __init__(self, *responses: FakeResponse | Exception):
        self.responses = list(responses)
        self.requests: list[tuple[object, float]] = []

    def open(self, request: object, timeout: float) -> FakeResponse:
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def transport(opener: FakeOpener, **values: object) -> ThemeHttpTransport:
    return ThemeHttpTransport(PAGES_BASE, opener=opener, **values)


def test_fetches_bounded_metadata_without_proxy_or_compression_headers() -> None:
    body = b'{"schemaVersion":1}'
    response = FakeResponse(body)
    opener = FakeOpener(response)

    result = transport(opener, connect_timeout=2.0, read_timeout=3.0).fetch_metadata(
        "themes/v1/hooandee-gallery/latest.json"
    )

    assert result == body
    request, timeout = opener.requests[0]
    assert timeout == 2.0
    assert request.get_header("Accept-encoding") == "identity"
    assert request.get_header("Cache-control") == "no-cache"
    assert response.read_timeout == 3.0


def test_follows_only_bounded_redirects_inside_the_fixed_prefix() -> None:
    target = f"{PAGES_BASE}/themes/v1/hooandee-gallery/latest.json"
    opener = FakeOpener(
        FakeResponse(status=302, location=target),
        FakeResponse(b"{}"),
    )

    assert transport(opener).fetch_metadata(
        "themes/v1/hooandee-gallery/latest.json"
    ) == b"{}"

    escaped = FakeOpener(
        FakeResponse(status=302, location="https://attacker.invalid/latest.json")
    )
    with pytest.raises(ThemeTransportError, match="redirect") as error:
        transport(escaped).fetch_metadata("themes/v1/hooandee-gallery/latest.json")
    assert error.value.code == "redirect_rejected"


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (FakeResponse(b"{}", status=503), "http_status"),
        (FakeResponse(b"{}", content_type="text/html"), "invalid_descriptor"),
        (FakeResponse(b"{}", content_length=65 * 1024), "descriptor_too_large"),
    ],
)
def test_rejects_bad_metadata_status_mime_and_length(
    response: FakeResponse,
    code: str,
) -> None:
    with pytest.raises(ThemeTransportError) as error:
        transport(FakeOpener(response)).fetch_metadata(
            "themes/v1/hooandee-gallery/latest.json"
        )
    assert error.value.code == code


def test_streams_and_atomically_verifies_the_artifact(tmp_path: Path) -> None:
    body = b"a verified zip payload"
    digest = hashlib.sha256(body).hexdigest()
    destination = tmp_path / "gallery.zip"
    opener = FakeOpener(FakeResponse(body, content_type="application/zip"))

    receipt = transport(opener).download_artifact(
        "themes/v1/hooandee-gallery/0.7.9/gallery.zip",
        destination,
        expected_size=len(body),
        expected_sha256=digest,
    )

    assert destination.read_bytes() == body
    assert receipt.path == destination
    assert receipt.size == len(body)
    assert receipt.sha256 == digest
    assert list(tmp_path.glob("*.part")) == []


@pytest.mark.parametrize(
    ("expected_size", "expected_digest", "code"),
    [
        (23, hashlib.sha256(b"payload").hexdigest(), "size_mismatch"),
        (7, "0" * 64, "hash_mismatch"),
    ],
)
def test_removes_partial_artifacts_after_verification_failure(
    tmp_path: Path,
    expected_size: int,
    expected_digest: str,
    code: str,
) -> None:
    with pytest.raises(ThemeTransportError) as error:
        transport(FakeOpener(FakeResponse(b"payload", content_type="application/zip"))).download_artifact(
            "themes/v1/hooandee-gallery/0.7.9/gallery.zip",
            tmp_path / "gallery.zip",
            expected_size=expected_size,
            expected_sha256=expected_digest,
        )
    assert error.value.code == code
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (ssl.SSLError("certificate failed"), "tls_error"),
        (TimeoutError("timed out"), "timeout"),
        (URLError("offline"), "offline"),
    ],
)
def test_maps_transport_failures_to_stable_codes(failure: Exception, code: str) -> None:
    with pytest.raises(ThemeTransportError) as error:
        transport(FakeOpener(failure)).fetch_metadata(
            "themes/v1/hooandee-gallery/latest.json"
        )
    assert error.value.code == code
