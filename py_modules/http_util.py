"""Shared HTTPS helper. Decky's bundled Python can ship without a usable CA
bundle, so the default SSL context fails to verify certs (CERTIFICATE_VERIFY_FAILED).
Load the system CA bundle explicitly. Used by self_updater and the bug reporter."""
from __future__ import annotations

import os
import ssl

_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ssl/cert.pem",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
)


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    for path in _CA_BUNDLES:
        if os.path.exists(path):
            try:
                ctx.load_verify_locations(path)
            except Exception:  # noqa: BLE001
                continue
            break
    return ctx
