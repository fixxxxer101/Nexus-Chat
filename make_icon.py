#!/usr/bin/env python3
"""Draw the Nexus Chat icon: a black tile, a green chat bubble,
two green dots and one orange dot. Pure stdlib (no PIL) so it runs
anywhere Python 3 does - install.sh uses it to render the icon
locally instead of shipping a binary.

Usage: python3 make_icon.py [chat|power] [output.png]
Two styles: "chat" (the Nexus Chat bubble) and "power" (the
Ollama Controller power symbol). Default: chat, icon.png.
Drawn at 1024, box-downsampled to 512 for smooth edges.
"""
import struct
import sys
import zlib

SIZE = 1024
OUT = 512
GREEN = (53, 255, 105)
ORANGE = (255, 140, 26)
BLACK = (5, 5, 5)
CLEAR = (0, 0, 0, 0)


def in_round_rect(x, y, x0, y0, x1, y1, r):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_circle(x, y, cx, cy, r):
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def in_triangle(x, y, ax, ay, bx, by, cx, cy):
    def sign(px, py, qx, qy, rx, ry):
        return (px - rx) * (qy - ry) - (qx - rx) * (py - ry)
    d1 = sign(x, y, ax, ay, bx, by)
    d2 = sign(x, y, bx, by, cx, cy)
    d3 = sign(x, y, cx, cy, ax, ay)
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def pixel(x, y):
    # black app tile
    if not in_round_rect(x, y, 16, 16, SIZE - 16, SIZE - 16, 200):
        return CLEAR
    base = BLACK
    # chat bubble: green outline (outer round-rect minus inner)
    if in_round_rect(x, y, 212, 292, 812, 692, 90) and \
            not in_round_rect(x, y, 238, 318, 786, 666, 70):
        base = GREEN
    # bubble tail: solid green triangle off the bottom-left
    if in_triangle(x, y, 330, 680, 470, 680, 330, 830):
        base = GREEN
    # three dots: green, green, orange
    for cx, col in ((382, GREEN), (512, GREEN), (642, ORANGE)):
        if in_circle(x, y, cx, 492, 52):
            base = col
    return base + (255,)


def pixel_power(x, y):
    # black app tile
    if not in_round_rect(x, y, 16, 16, SIZE - 16, SIZE - 16, 200):
        return CLEAR
    base = BLACK
    cx, cy = 512, 540
    d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    # ring with a gap at the top where the stem passes through
    in_gap = y < cy - 100 and abs(x - cx) < 100
    if 150 <= d <= 202 and not in_gap:
        base = GREEN
    # the stem: orange, dropping from above into the ring
    if in_round_rect(x, y, 478, 262, 546, 560, 34):
        base = ORANGE
    return base + (255,)


PIXELS = {"chat": pixel, "power": pixel_power}


def render(style="chat"):
    rows = []
    step = SIZE // OUT
    for oy in range(OUT):
        row = bytearray()
        for ox in range(OUT):
            # box average over the step x step block
            acc = [0, 0, 0, 0]
            n = 0
            for dy in range(step):
                for dx in range(step):
                    p = PIXELS[style](ox * step + dx, oy * step + dy)
                    # un-premultiply-ish: weight by alpha
                    a = p[3] / 255.0
                    acc[0] += p[0] * a
                    acc[1] += p[1] * a
                    acc[2] += p[2] * a
                    acc[3] += p[3]
                    n += 1
            alpha = acc[3] / n
            if alpha > 0:
                row += bytes((int(acc[0] / n * 255 / max(alpha, 1)),
                              int(acc[1] / n * 255 / max(alpha, 1)),
                              int(acc[2] / n * 255 / max(alpha, 1)),
                              int(alpha)))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(b"\x00" + bytes(row))
    return b"".join(rows)


def png_bytes(style="chat"):
    raw = render(style)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

    ihdr = struct.pack(">IIBBBBB", OUT, OUT, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    args = sys.argv[1:]
    style = "chat"
    if args and args[0] in PIXELS:
        style = args.pop(0)
    out = args[0] if args else "icon.png"
    with open(out, "wb") as f:
        f.write(png_bytes(style))
    print("wrote", out, "(%s)" % style)
