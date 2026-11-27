#!/usr/bin/env python3
"""desk-radio web page: pick a station on any computer or phone and it plays there.

The XU4 only serves the page and the station list; each browser streams the
station itself. Uses only Python's standard library, so there is nothing to install.

    GET  /                 the radio page
    GET  /api/stations     {"stations": [{"name": "groovesalad", "url": "https://..."}, ...]}

Stations come from stations.txt next to this file ('name = url' per line), read on
every request, so edits show up on the next page load without a restart.

Listens on 0.0.0.0:8080 by default; set DESK_RADIO_HOST / DESK_RADIO_PORT to change.

If DESK_RADIO_PASSWORD is set (e.g. in .env, loaded by the systemd service), every
request needs that password via HTTP Basic Auth; the browser asks once and remembers.
Any username is accepted. Without it, the page is open to anyone who can reach it.
"""
import base64
import binascii
import hmac
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = os.environ.get("DESK_RADIO_HOST", "0.0.0.0")
PORT = int(os.environ.get("DESK_RADIO_PORT", "8080"))
PASSWORD = os.environ.get("DESK_RADIO_PASSWORD", "")
PAGE = HERE / "web" / "index.html"
STATIONS_FILE = HERE / "stations.txt"


def load_stations():
    """Read 'name = url' lines from stations.txt, skipping blanks and # comments."""
    stations = []
    for line in STATIONS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, url = line.split("=", 1)
        stations.append({"name": name.strip(), "url": url.strip()})
    return stations


class Handler(BaseHTTPRequestHandler):
    server_version = "desk-radio"

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/":
            self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/stations":
            self._json(HTTPStatus.OK, {"stations": load_stations()})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _authorized(self):
        """Check the Basic Auth password; on failure send 401 so the browser asks for it."""
        if not PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        scheme, _, encoded = header.partition(" ")
        given = ""
        if scheme.lower() == "basic":
            try:
                given = base64.b64decode(encoded, validate=True).decode("utf-8").partition(":")[2]
            except (binascii.Error, UnicodeDecodeError):
                given = ""
        if hmac.compare_digest(given.encode(), PASSWORD.encode()):
            return True
        body = json.dumps({"error": "Password required"}).encode()
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="Desk Radio", charset="UTF-8"')
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def _json(self, status, data):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Log only failed requests, so the journal stays quiet.
        if len(args) > 1 and str(args[1])[:1] in "45":
            super().log_message(fmt, *args)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"desk-radio web page on http://{HOST}:{PORT}", flush=True)
    if not PASSWORD:
        print("WARNING: DESK_RADIO_PASSWORD is not set; the page is open to anyone who can reach it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
