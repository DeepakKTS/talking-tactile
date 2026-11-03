"""Serves the Gate B touch-test page (this folder) over HTTPS with the phone certificate that
npm run cert:phone makes, and with security headers. Every interface, so the iPhone on the same
network can open it; nothing outside this folder is served.

    python3 spikes/tracking/serve.py            # https on :8443
    python3 spikes/tracking/serve.py --http     # plain http, for a laptop browser

e2e_check.py serves the page with the same Handler, so the headless checks run under the same
Content-Security-Policy. The page loads MediaPipe's bundle and wasm from jsDelivr and the hand
model from Google's model storage; nothing else leaves this origin."""

from __future__ import annotations

import argparse
import os
import http.server
import ssl
from pathlib import Path

HERE = Path(__file__).resolve().parent
CERTS = HERE.parent.parent / "apps" / "web" / ".certs"
CDN = "https://cdn.jsdelivr.net"
MODELS = "https://storage.googleapis.com"
CSP = "; ".join([
    "default-src 'self'",
    f"script-src 'self' {CDN} 'wasm-unsafe-eval'",
    "worker-src 'self' blob:",
    f"connect-src 'self' {CDN} {MODELS}",
    "img-src 'self' data: blob:",
    "media-src 'self' blob: mediastream:",
    "style-src 'self' 'unsafe-inline'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
if os.environ.get("TT_CSP") != "off":  # TT_CSP=off: the one-command rollback in docs/DEMO.md
    HEADERS["Content-Security-Policy"] = CSP


class Handler(http.server.SimpleHTTPRequestHandler):
    """This folder only, with HEADERS on every response, and no request log."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(HERE), **kwargs)  # type: ignore[arg-type]

    def end_headers(self) -> None:
        for name, value in HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--http", action="store_true", help="plain http (no certificate)")
    args = ap.parse_args()
    server = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    scheme = "http"
    if not args.http:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(CERTS / "phone.pem", CERTS / "phone-key.pem")
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    print(f"Gate B touch test on {scheme}://<this Mac>:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
