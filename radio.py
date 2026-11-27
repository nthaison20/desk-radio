#!/usr/bin/env python3
"""desk-radio: play, stop and check internet radio stations through MPD."""
import sys
from contextlib import contextmanager
from pathlib import Path

from mpd import MPDClient

MPD_HOST = "127.0.0.1"
MPD_PORT = 6600
STATIONS_FILE = Path(__file__).resolve().with_name("stations.txt")


def load_stations():
    """Read 'name = url' lines from stations.txt, skipping blanks and # comments."""
    stations = {}
    for line in STATIONS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, url = line.split("=", 1)
        stations[name.strip()] = url.strip()
    return stations


@contextmanager
def connect():
    """Open a connection to MPD and always close it afterwards."""
    client = MPDClient()
    client.timeout = 5
    client.connect(MPD_HOST, MPD_PORT)
    try:
        yield client
    finally:
        client.disconnect()


def play(name):
    """Play a station by name. Raises KeyError if the name is not in stations.txt."""
    stations = load_stations()
    if name not in stations:
        raise KeyError(name)
    with connect() as client:
        client.clear()
        client.add(stations[name])
        client.play()


def stop():
    with connect() as client:
        client.stop()


def now_playing():
    """Return {'station': name or None, 'state': 'play'|'stop'|'pause', 'error': str or None}."""
    with connect() as client:
        state = client.status()
        song = client.currentsong()
    url = song.get("file")
    names = {u: n for n, u in load_stations().items()}
    return {
        "station": names.get(url, url),
        "state": state["state"],
        "error": state.get("error"),
    }


def main():
    args = sys.argv[1:]
    if args[:1] == ["play"] and len(args) == 2:
        try:
            play(args[1])
        except KeyError:
            sys.exit(f"Unknown station '{args[1]}'. Known: {', '.join(load_stations())}")
        print(f"Playing {args[1]}")
    elif args == ["stop"]:
        stop()
        print("Stopped")
    elif args == ["status"]:
        info = now_playing()
        print(f"{info['station'] or 'nothing'} [{info['state']}]")
        if info["error"]:
            print(f"MPD error: {info['error']}")
    elif args == ["list"]:
        for name in load_stations():
            print(name)
    else:
        sys.exit("Usage: radio.py play <station> | stop | status | list")


if __name__ == "__main__":
    main()
