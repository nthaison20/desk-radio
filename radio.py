#!/usr/bin/env python3
"""desk-radio: play, stop and check internet radio stations through MPD."""
import sys
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


def connect():
    client = MPDClient()
    client.connect(MPD_HOST, MPD_PORT)
    return client


def play(name):
    stations = load_stations()
    if name not in stations:
        sys.exit(f"Unknown station '{name}'. Known: {', '.join(stations)}")
    client = connect()
    client.clear()
    client.add(stations[name])
    client.play()
    client.disconnect()
    print(f"Playing {name}")


def stop():
    client = connect()
    client.stop()
    client.disconnect()
    print("Stopped")


def status():
    client = connect()
    state = client.status()
    song = client.currentsong()
    client.disconnect()
    url = song.get("file")
    names = {u: n for n, u in load_stations().items()}
    print(f"{names.get(url, url or 'nothing')} [{state['state']}]")
    if "error" in state:
        print(f"MPD error: {state['error']}")


def main():
    args = sys.argv[1:]
    if args[:1] == ["play"] and len(args) == 2:
        play(args[1])
    elif args == ["stop"]:
        stop()
    elif args == ["status"]:
        status()
    elif args == ["list"]:
        for name in load_stations():
            print(name)
    else:
        sys.exit("Usage: radio.py play <station> | stop | status | list")


if __name__ == "__main__":
    main()
