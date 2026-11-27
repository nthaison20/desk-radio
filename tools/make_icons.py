#!/usr/bin/env python3
"""Draw the desk-radio app icon (a 16x16 pixel-art radio) and save it as PNGs.

Standard library only. Run from the repo root:  python3 tools/make_icons.py
Writes web/icons/: apple-touch-icon.png (180, used by iPhone), icon-192.png,
icon-512.png, and icon-maskable-512.png (extra margin for Android's shaped icons).
"""
import struct
import zlib
from pathlib import Path

# . background   B radio body   A amber outline/grille   D dim grille   L bright light
ART = [
    "................",
    "............L...",
    "...........A....",
    "..........A.....",
    "..AAAAAAAAAAAA..",
    "..ABBBBBBBBBBA..",
    "..ABAAAABLLLBA..",
    "..ABDDDDBBBBBA..",
    "..ABAAAABBBBBA..",
    "..ABDDDDBLBLBA..",
    "..ABAAAABBBBBA..",
    "..ABBBBBBBBBBA..",
    "..AAAAAAAAAAAA..",
    "...A........A...",
    "................",
    "................",
]
COLOURS = {
    ".": (0x0C, 0x0A, 0x06),  # page background
    "B": (0x2A, 0x1F, 0x0C),
    "A": (0xFF, 0xB0, 0x00),  # page accent amber
    "D": (0x6A, 0x4B, 0x14),
    "L": (0xFF, 0xE0, 0x8A),
}


def write_png(path, size, scale):
    """Draw ART scaled up by `scale` (hard pixel edges), centred on a `size` x `size` square."""
    art_px = len(ART) * scale
    margin = (size - art_px) // 2
    bg = COLOURS["."]
    rows = []
    for y in range(size):
        ay = (y - margin) // scale
        row = bytearray(b"\x00")  # PNG filter type 0 for this row
        for x in range(size):
            ax = (x - margin) // scale
            inside = 0 <= ay < len(ART) and 0 <= ax < len(ART) and y >= margin and x >= margin
            row += bytes(COLOURS[ART[ay][ax]] if inside else bg)
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))  # 8-bit RGB
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
           + chunk(b"IEND", b""))
    path.write_bytes(png)
    print(f"wrote {path} ({size}x{size}, {len(png)} bytes)")


def main():
    out = Path(__file__).resolve().parent.parent / "web" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    write_png(out / "apple-touch-icon.png", 180, 10)    # 160 px of art, 10 px margin
    write_png(out / "icon-192.png", 192, 11)            # 176 px of art
    write_png(out / "icon-512.png", 512, 30)            # 480 px of art
    write_png(out / "icon-maskable-512.png", 512, 24)   # 384 px: inside Android's 80% safe zone


if __name__ == "__main__":
    main()
