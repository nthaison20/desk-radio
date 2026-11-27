# Changelog

A log of what has changed in desk-radio: the app itself (tracked in git) and the
setup of the ODROID-XU4 that runs it (which git doesn't track). Newest first.
Commit IDs link each entry to its change in the history.

## Where things stand

Desk Radio is a small web app served by the XU4. You open it on a phone or computer,
sign in, and pick a station; **the station plays on that device**, not on the XU4.

- **Mine / Explore / Map** tabs: your saved stations, a search of the open
  [Radio Browser](https://www.radio-browser.info) directory, and an 8-bit pixel map.
- **Pixel map**: world → country → station spots, with zoom and pan, and a search box
  for countries and cities.
- **Current song** shown while playing, also on the iPhone lock screen.
- **Installs on iPhone** as a home-screen app over HTTPS (via Tailscale).
- **Sign-in page**, sessions last 30 days.
- Runs on Python's standard library only (`web.py`); nothing to install on the XU4.

---

## 2026-11-27

### Changed: volume follows the device (`58df9c6`)
- Removed the in-page volume slider. Playback runs at full level; loudness comes from the
  phone's volume buttons or the computer's volume. (iPhone never let the slider work anyway.)
- Any previously saved slider level is cleared.

### Added: current song (`feecd86`)
- While a station plays, the Now card shows **♪ Artist – Song**, refreshed about every 20 s.
- On the iPhone lock screen and Control Center, the song is the title and the station the subtitle.
- The XU4 reads the title many stations embed in their stream ("ICY" metadata) and caches it
  for 15 s, so devices on the same station share one check.
- Safety: only public internet addresses are fetched (also after redirects), so the feature
  can't be used to reach devices on the home network. Expired-certificate streams are refused.
- Not available for HLS stations (e.g. BBC) or stations that don't send titles.

### Added: iPhone app, sign-in page, map search (`cf47e40`)
- **Home-screen app**: pixel-art radio icon, name "Desk Radio", opens full-screen.
  Icons are drawn by `tools/make_icons.py` (standard library only).
- **Sign-in page** replaces the browser's password pop-up. Each device stays signed in for
  30 days; changing the password signs everyone out; wrong passwords are slowed down.
  A **Sign out** button sits at the bottom of the page.
- **Map search**: countries match instantly as you type (on the device); cities are looked up
  when you press **Go**, via OpenStreetMap's Nominatim (max one lookup per second, cached a day),
  then the map flies there and lists nearby stations.
- **"Find more stations in …"** button when a place has few mapped stations: runs that
  country's search in Explore.

## 2026-11-26

### Added: zoom and pan on the pixel map (`1a0078a`)
- Drag to move, pinch / mouse wheel / **+ −** buttons / double-tap to zoom.
- Real zoom: the map is redrawn at each zoom, so pixels stay chunky while detail increases.
- Switched to a Mercator-style projection; the map box is about 3:4, so the world fills it.
- Station markers become tappable "+" once zoomed in; tapping a country flies to it;
  **◀ World** flies back.

### Changed: 8-bit amber redesign with a pixel map (`9f44b6c`)
- Whole page uses an amber-on-black terminal look with a pixel font for headings.
- The map is drawn by the page itself from public-domain country outlines
  (Natural Earth via world-atlas 2.0.2, stored in the repo), replacing Leaflet and
  OpenStreetMap tiles. World view → tap a country → its stations as markers.
- Fixed during testing: views for countries with far-off territories (e.g. France),
  shapes crossing the date line, offshore stations assigned to the wrong country,
  and tiny countries missing from the world view.

### Added: Map tab (`0904678`)
- First map version: ~5,000 popular stations with known locations as dots, grouped by city,
  on a Leaflet / OpenStreetMap map. (Replaced by the pixel map in `9f44b6c`.)
- The XU4 fetches station locations once a day and sends them compressed.

### Added: Explore (`79b41b1`)
- Search the Radio Browser directory by name, genre or country; "Load more" pages.
- Star (☆) any station to save it to **My stations** (`my-stations.json` on the XU4).
- The XU4 follows Radio Browser's rules: server discovery, a descriptive User-Agent,
  and reporting plays so popular stations rank higher.

### Changed: play in the browser on each device; MPD removed (`fd774ad`)
- Stations now play on the phone or computer that opens the page, not on the XU4.
- Removed the MPD-based `radio.py` and the MPD stand-in config.

### Added: password for the web page (`c78af5c`)
- Optional password (from `.env`) using the browser's password pop-up.
  (Replaced by the sign-in page in `cf47e40`.) Added `.env.example`.

### Added: web control page (`5fa599b`)
- First web page: pick a station from any computer or phone, controlling MPD on the XU4.
  (Replaced by in-browser playback in `fd774ad`.)

### Added: `radio.py` (`eadb275`)
- Command-line play / stop / status / list for stations in `stations.txt`, via MPD.
  (Removed in `fd774ad`.)

## 2026-11-25

### Added: development setup (`00070ed`)
- A silent MPD stand-in config for development on the XU4 (removed in `fd774ad`).
- `.gitattributes`: store all text files with LF line endings.
- `.gitignore`: ignore `.env` (secrets).

### Initial commit (`3f55f8e`)
- Repository created with README, LICENSE and a Python `.gitignore`.

---

## XU4 setup (not tracked in git)

Changes made directly on the ODROID-XU4 (Armbian, Debian trixie), in order.

| Date | Change | Status |
|---|---|---|
| 2026-11-26 | Cloned the repo to `~/desk-radio` | In use |
| 2026-11-26 | Installed `mpd`, `mpc`; ran the silent MPD stand-in | Removed 2026-11-26 |
| 2026-11-26 | Installed `python3-mpd` for `radio.py` | Removed 2026-11-26 |
| 2026-11-26 | Set git name/email (privacy-preserving GitHub noreply address) | In use |
| 2026-11-26 | Installed GitHub CLI (`gh`) to push from the XU4 | Removed 2026-11-26; pushes are done from the laptop |
| 2026-11-26 | User service `desk-radio-mpd` (MPD stand-in at boot) | Removed 2026-11-26 |
| 2026-11-26 | Enabled lingering for the user, so user services start at boot without logging in | In use |
| 2026-11-26 | User service `desk-radio-web` (runs `web.py` at boot, restarts on failure) | In use |
| 2026-11-26 | `~/desk-radio/.env` with the password (`chmod 600`, gitignored); service reads it via `EnvironmentFile` | In use |
| 2026-11-26 | Cleared apt's download cache (`apt clean`) after removing MPD and `gh` | Done |
| 2026-11-27 | Tailscale HTTPS: `tailscale serve --bg 8080`, giving the app an HTTPS address on the tailnet | In use |

### Updating the XU4 after a push

```bash
cd ~/desk-radio && git pull && systemctl --user restart desk-radio-web && systemctl --user is-active desk-radio-web
```

### The web service (`~/.config/systemd/user/desk-radio-web.service`)

```ini
[Unit]
Description=desk-radio web page
After=network-online.target

[Service]
EnvironmentFile=-%h/desk-radio/.env
ExecStart=/usr/bin/python3 %h/desk-radio/web.py
Restart=on-failure

[Install]
WantedBy=default.target
```
