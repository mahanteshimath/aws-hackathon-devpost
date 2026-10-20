"""Local dev server: serves the TV app, phone app, API and generated files on your LAN.

    .venv/bin/python backend/dev_server.py
    # TV (Fire TV WebView or browser):  http://<your-mac-ip>:8787/tv/
"""

from __future__ import annotations

import logging
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crayon.api import MAX_UPLOAD, Request, handle  # noqa: E402
from crayon.config import settings  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _serve(self) -> None:
        parts = urlsplit(self.path)
        length = int(self.headers.get("content-length") or 0)
        if length > MAX_UPLOAD + 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else b""
        req = Request(
            method=self.command,
            path=parts.path,
            query=dict(parse_qsl(parts.query)),
            headers={k.lower(): v for k, v in self.headers.items()},
            body=body,
        )
        resp = handle(req)
        self.send_response(resp.status)
        for k, v in resp.headers.items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(resp.body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(resp.body)

    do_GET = do_POST = do_PUT = do_OPTIONS = do_HEAD = _serve

    def log_message(self, fmt: str, *args) -> None:
        if "/api/stories/" in (args[0] if args else "") and " 200 " in fmt % args:
            return  # TV polls every second; keep the console readable
        logging.getLogger("http").info(fmt, *args)


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = settings()
    server = ThreadingHTTPServer(("0.0.0.0", cfg.port), Handler)
    ip = lan_ip()
    print(f"\n  Crayon Cinema dev server  (mode={cfg.mode}, storage={cfg.storage})")
    print(f"  TV:    http://{ip}:{cfg.port}/tv/")
    print(f"  Phone: scan the QR code on the TV screen\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
