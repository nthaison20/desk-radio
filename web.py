#!/usr/bin/env python3
"""desk-radio web page: find and play internet radio on any computer or phone.

The XU4 serves the page, keeps your saved stations, and searches the open
Radio Browser directory (https://www.radio-browser.info) on the page's behalf.
Each browser streams the station itself. Standard library only: nothing to install.

    GET  /                       the radio page
    GET  /api/stations           your saved stations {"stations": [...]}
    POST /api/stations           save one   body {"id", "name", "url", ...}
    POST /api/stations/remove    remove one body {"id"}
    GET  /api/search?q=&by=&offset=
                                 search Radio Browser; by = name | tag | country;
                                 empty q lists the most popular stations
    POST /api/click              body {"id"}: tell Radio Browser a station was played
    GET  /api/map                popular stations that have a location, grouped into
                                 places {"places": [{"lat", "lon", "stations": [...]}]};
                                 fetched once and cached for a day

Saved stations live in my-stations.json next to this file (gitignored). The first
time it is missing, it is seeded from stations.txt ('name = url' per line).

Listens on 0.0.0.0:8080 by default; set DESK_RADIO_HOST / DESK_RADIO_PORT to change.

If DESK_RADIO_PASSWORD is set (e.g. in .env, loaded by the systemd service), every
request needs that password via HTTP Basic Auth; the browser asks once and remembers.
Any username is accepted. Without it, the page is open to anyone who can reach it.
"""
import base64
import binascii
import gzip
import hmac
import json
import os
import random
import re
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
HOST = os.environ.get("DESK_RADIO_HOST", "0.0.0.0")
PORT = int(os.environ.get("DESK_RADIO_PORT", "8080"))
PASSWORD = os.environ.get("DESK_RADIO_PASSWORD", "")
PAGE = HERE / "web" / "index.html"
DEFAULT_STATIONS = HERE / "stations.txt"
MY_STATIONS = HERE / "my-stations.json"

USER_AGENT = "desk-radio/1.0"
RB_TIMEOUT = 8
PAGE_SIZE = 40
MAX_BODY = 4096
MAP_STATIONS = 5000        # most popular located stations shown on the map
MAP_CACHE_SECONDS = 24 * 3600
MAP_GRID = 0.1             # degrees (~10 km): stations closer than this share one map dot
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SEARCH_FIELDS = {"name", "tag", "country"}


class RadioBrowser:
    """Minimal Radio Browser client following its rules: DNS server discovery,
    random server order with failover, and a descriptive User-Agent."""

    def __init__(self):
        self._servers = []
        self._lock = threading.Lock()

    @staticmethod
    def _discover():
        names = set()
        try:
            for info in socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP):
                try:
                    name = socket.gethostbyaddr(info[4][0])[0]
                except OSError:
                    continue
                if name.endswith(".radio-browser.info"):
                    names.add(name)
        except OSError:
            pass
        if not names:  # DNS route failed: ask the round-robin host for the list instead
            try:
                req = Request("https://all.api.radio-browser.info/json/servers", headers={"User-Agent": USER_AGENT})
                with urlopen(req, timeout=RB_TIMEOUT) as res:
                    names = {s["name"] for s in json.load(res) if s.get("name", "").endswith(".radio-browser.info")}
            except (OSError, ValueError, KeyError, TypeError):
                pass
        servers = [f"https://{name}" for name in names]
        random.shuffle(servers)
        return servers

    def get(self, path, params=None):
        with self._lock:
            if not self._servers:
                self._servers = self._discover()
            servers = list(self._servers)
        if not servers:
            raise URLError("no Radio Browser servers found")
        query = f"?{urlencode(params)}" if params else ""
        last_error = None
        for base in servers:
            try:
                req = Request(base + path + query, headers={"User-Agent": USER_AGENT})
                with urlopen(req, timeout=RB_TIMEOUT) as res:
                    return json.load(res)
            except (OSError, ValueError) as exc:  # URLError and timeouts are OSErrors
                last_error = exc
                with self._lock:  # try this server last next time
                    if base in self._servers:
                        self._servers.remove(base)
                        self._servers.append(base)
        with self._lock:
            self._servers = []  # every server failed: rediscover on the next request
        raise last_error


radio_browser = RadioBrowser()


def trim_station(s):
    """Keep only what the page needs from a Radio Browser station record."""
    return {
        "id": s.get("stationuuid", ""),
        "name": (s.get("name") or "").strip() or "Unnamed station",
        "url": s.get("url_resolved") or s.get("url") or "",
        "favicon": s.get("favicon") or "",
        "country": s.get("country") or "",
        "countrycode": s.get("countrycode") or "",
        "tags": [t.strip() for t in (s.get("tags") or "").split(",") if t.strip()][:4],
        "codec": s.get("codec") or "",
        "bitrate": s.get("bitrate") or 0,
    }


# ---- map -------------------------------------------------------------------

_map_lock = threading.Lock()
_map_cache = {"time": 0.0, "body": None}  # body = gzipped JSON, ready to send


def _build_map():
    results = radio_browser.get("/json/stations/search", {
        "has_geo_info": "true", "hidebroken": "true", "order": "clickcount",
        "reverse": "true", "limit": str(MAP_STATIONS),
    })
    places = {}
    for s in results:
        lat, lon = s.get("geo_lat"), s.get("geo_long")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        station = trim_station(s)
        if not station["id"] or not station["url"]:
            continue
        key = (round(lat / MAP_GRID), round(lon / MAP_GRID))
        place = places.setdefault(key, {"lat": round(lat, 3), "lon": round(lon, 3), "stations": []})
        place["stations"].append(station)  # results are most-popular first, so lists stay sorted
    data = {"places": list(places.values()), "count": sum(len(p["stations"]) for p in places.values())}
    return gzip.compress(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def map_data():
    """Gzipped map JSON, rebuilt at most once a day; serves the old copy if a rebuild fails."""
    with _map_lock:  # one rebuild at a time; other requests wait for it instead of piling on
        fresh = time.time() - _map_cache["time"] < MAP_CACHE_SECONDS
        if _map_cache["body"] is None or not fresh:
            try:
                _map_cache["body"] = _build_map()
                _map_cache["time"] = time.time()
            except (OSError, ValueError):
                if _map_cache["body"] is None:
                    raise
        return _map_cache["body"]


# ---- saved stations -------------------------------------------------------

_stations_lock = threading.Lock()


def _seed_stations():
    stations = []
    if DEFAULT_STATIONS.exists():
        for line in DEFAULT_STATIONS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, url = line.split("=", 1)
            stations.append({"id": f"local:{name.strip()}", "name": name.strip(), "url": url.strip()})
    return stations


def load_my_stations():
    with _stations_lock:
        if MY_STATIONS.exists():
            return json.loads(MY_STATIONS.read_text(encoding="utf-8"))
        return _seed_stations()


def _save(stations):
    tmp = MY_STATIONS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stations, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, MY_STATIONS)  # atomic: a crash never leaves a half-written file


def add_station(station):
    with _stations_lock:
        stations = json.loads(MY_STATIONS.read_text(encoding="utf-8")) if MY_STATIONS.exists() else _seed_stations()
        if not any(s["id"] == station["id"] for s in stations):
            stations.append(station)
            _save(stations)
        return stations


def remove_station(station_id):
    with _stations_lock:
        stations = json.loads(MY_STATIONS.read_text(encoding="utf-8")) if MY_STATIONS.exists() else _seed_stations()
        kept = [s for s in stations if s["id"] != station_id]
        _save(kept)
        return kept


def clean_station(body):
    """Validate a station sent by the page; return a tidy dict or None."""
    sid, name, url = body.get("id"), body.get("name"), body.get("url")
    if not all(isinstance(v, str) and v.strip() for v in (sid, name, url)):
        return None
    if not url.startswith(("http://", "https://")) or len(url) > 2000 or len(name) > 200 or len(sid) > 200:
        return None
    station = {"id": sid.strip(), "name": name.strip(), "url": url.strip()}
    for key in ("favicon", "country", "countrycode", "codec"):
        if isinstance(body.get(key), str) and len(body[key]) <= 2000:
            station[key] = body[key]
    if isinstance(body.get("tags"), list):
        station["tags"] = [t for t in body["tags"] if isinstance(t, str) and len(t) <= 60][:4]
    if isinstance(body.get("bitrate"), int):
        station["bitrate"] = body["bitrate"]
    return station


# ---- HTTP ----------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "desk-radio"

    def do_GET(self):
        if not self._authorized():
            return
        url = urlsplit(self.path)
        if url.path == "/":
            self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/stations":
            self._json(HTTPStatus.OK, {"stations": load_my_stations()})
        elif url.path == "/api/search":
            self._search(parse_qs(url.query))
        elif url.path == "/api/map":
            self._map()
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self):
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        body = self._read_json()
        if body is None:
            return
        if path == "/api/stations":
            station = clean_station(body)
            if station is None:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Station needs an id, a name and an http(s) URL"})
                return
            self._json(HTTPStatus.OK, {"stations": add_station(station)})
        elif path == "/api/stations/remove":
            if not isinstance(body.get("id"), str):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Missing station id"})
                return
            self._json(HTTPStatus.OK, {"stations": remove_station(body["id"])})
        elif path == "/api/click":
            station_id = body.get("id")
            if isinstance(station_id, str) and UUID_RE.match(station_id):
                try:
                    radio_browser.get(f"/json/url/{station_id}")
                except (OSError, ValueError):
                    pass  # counting a click is best-effort; playback doesn't depend on it
            self._json(HTTPStatus.OK, {"ok": True})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _search(self, query):
        q = (query.get("q") or [""])[0].strip()[:100]
        by = (query.get("by") or ["name"])[0]
        try:
            offset = max(0, min(int((query.get("offset") or ["0"])[0]), 10000))
        except ValueError:
            offset = 0
        if by not in SEARCH_FIELDS:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "by must be name, tag or country"})
            return
        params = {"hidebroken": "true", "order": "clickcount", "reverse": "true",
                  "limit": str(PAGE_SIZE), "offset": str(offset)}
        if q and by == "tag":
            # Exact tag match ("jazz" means tagged jazz, not any tag containing "jazz"); tags are lowercase.
            params["tag"] = q.lower()
            params["tagExact"] = "true"
        elif q:
            params[by] = q
        try:
            results = radio_browser.get("/json/stations/search", params)
        except (OSError, ValueError) as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": f"Station directory unavailable: {exc}"})
            return
        stations = [trim_station(s) for s in results if isinstance(s, dict)]
        stations = [s for s in stations if s["id"] and s["url"]]
        self._json(HTTPStatus.OK, {"stations": stations, "more": len(results) == PAGE_SIZE})

    def _map(self):
        try:
            body = map_data()
        except (OSError, ValueError) as exc:
            self._json(HTTPStatus.BAD_GATEWAY, {"error": f"Station directory unavailable: {exc}"})
            return
        if "gzip" not in self.headers.get("Accept-Encoding", ""):
            self._send(HTTPStatus.OK, gzip.decompress(body), "application/json")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

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

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Request too large"})
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
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
