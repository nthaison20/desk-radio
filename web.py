#!/usr/bin/env python3
"""desk-radio web control: a small page for any computer or phone on the network.

Serves web/index.html plus a tiny JSON API that drives MPD through radio.py.
Uses only Python's standard library, so there is nothing extra to install.

    GET  /                 the control page
    GET  /api/stations     {"stations": ["groovesalad", ...]}
    GET  /api/status       {"station": ..., "state": ..., "error": ...}
    POST /api/play         body {"station": "groovesalad"}  -> status
    POST /api/stop         -> status

Listens on 0.0.0.0:8080 by default; set DESK_RADIO_HOST / DESK_RADIO_PORT to change.
"""
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mpd import MPDError

import radio

HOST = os.environ.get("DESK_RADIO_HOST", "0.0.0.0")
PORT = int(os.environ.get("DESK_RADIO_PORT", "8080"))
PAGE = Path(__file__).resolve().parent / "web" / "index.html"
MAX_BODY = 4096


class Handler(BaseHTTPRequestHandler):
    server_version = "desk-radio"

    def do_GET(self):
        if self.path == "/":
            self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/stations":
            self._json(HTTPStatus.OK, {"stations": list(radio.load_stations())})
        elif self.path == "/api/status":
            self._with_mpd(lambda: None)
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/api/play":
            body = self._read_json()
            if body is None:
                return
            station = body.get("station")
            if station not in radio.load_stations():
                self._json(HTTPStatus.NOT_FOUND, {"error": f"Unknown station: {station}"})
                return
            self._with_mpd(lambda: radio.play(station))
        elif self.path == "/api/stop":
            self._with_mpd(radio.stop)
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _with_mpd(self, action):
        """Run an MPD action, then reply with the current status (or 503 if MPD is down)."""
        try:
            action()
            self._json(HTTPStatus.OK, radio.now_playing())
        except (MPDError, OSError) as exc:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": f"Can't reach MPD: {exc}"})

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Request too large"})
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = None
        if not isinstance(body, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Expected a JSON object"})
            return None
        return body

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
        # Log only failed requests, so the journal doesn't fill with status polls.
        if len(args) > 1 and str(args[1])[:1] in "45":
            super().log_message(fmt, *args)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"desk-radio web control on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
