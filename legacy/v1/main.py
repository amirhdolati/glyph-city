#!/usr/bin/env python3
"""Glyph City — a walkable 3D town rendered with the RendASCII engine.

The town is real 3D geometry (textured quads + billboard sprites) fed to
the vendored RendASCII engine (z-buffered rasterizer, MIT licensed).
This module drives the engine, paints its character frames with the
day/night palette and weather, and draws them in the terminal.

  python3 main.py                  play in this terminal
  python3 main.py --shot           write one frame to shot.ppm and exit
  python3 main.py --truecolor      force 24-bit color frames
  python3 main.py --256            force 256-color frames (old terminals)

In game:
  W/A/S/D      move (hold Shift to sprint)   Q/E or arrows: turn
  mouse        look (M toggles, - / = sensitivity)
  T pause clock   Y skip 3h   N weather   R rain   C color mode   Ctrl-C quit
"""

from __future__ import annotations

import math
import os
import queue
import select
import sys
import threading
import time
from dataclasses import dataclass, field

FOV = math.radians(60)
EYE = 1.65
MOVE = 4.2
TURN = 1.8
SPRINT = 1.9
CELL_SENS = 0.020
PX_SENS = 0.004
DAY_LEN = 150.0
NEAR, FAR = 0.4, 60.0
# Vertical focal ratio: terminal cells are ~2x taller than wide, so the
# vertical focal length is scaled by the cell aspect (w/h) to keep world
# proportions natural. Recomputed per frame from the real cell size.
_VFOV = [0.5]


def _cell_aspect(cell_w, cell_h):
    try:
        a = float(cell_w) / float(cell_h)
    except (TypeError, ZeroDivisionError):
        return 0.5
    return a if 0.3 <= a <= 0.8 else 0.5

# . street  + sidewalk  , ; grass  digits = building lots
MAP = [
    "33333333333333333333333333333333333333",
    "3++++++++......++++++++......++++++++3",
    "3+,,,,,,+......+777777+......+444444+3",
    "3+,,;;,,+......+777777+......+444444+3",
    "3+,,;,,,+......+777777+......+444444+3",
    "3+,,,,,,+......+777777+......+444444+3",
    "3++++++++......++++++++......++++++++3",
    "3....................................3",
    "3....................................3",
    "3....................................3",
    "3++++++++......++++++++......++++++++3",
    "3++++++++......+555555+......+666666+3",
    "3++++++++......+555555+......+666666+3",
    "3++++++++......+555555+......+666666+3",
    "3++++++++......+555555+......+666666+3",
    "3....................................3",
    "3....................................3",
    "3....................................3",
    "3++++++++......++++++++......++++++++3",
    "3+333333+......+222222+......+888888+3",
    "3+333333+......+222222+......+888888+3",
    "3+333333+......+222222+......+888888+3",
    "3++++++++......++++++++......++++++++3",
    "3....................................3",
    "3....................................3",
    "3....................................3",
    "3++++++++......++++++++......++++++++3",
    "3+444444+......+666666+......+555555+3",
    "3+444444+......+666666+......+555555+3",
    "33333333333333333333333333333333333333",
]
H = len(MAP)
W = len(MAP[0])
MAP = [row.ljust(W, "3")[:W] for row in MAP]

LOT = {  # digit -> (stories, facade RGB)
    "2": (1, (196, 98, 74)),
    "3": (2, (152, 156, 166)),
    "4": (2, (56, 132, 164)),
    "5": (3, (162, 70, 130)),
    "6": (2, (222, 178, 96)),
    "7": (4, (66, 148, 158)),
    "8": (1, (208, 156, 112)),
}
WNAMES = ("CLEAR", "RAIN", "OVERCAST", "STORM", "SNOW")
LAMPS = [
    (1.9, 2.6), (8.1, 5.4), (9.5, 7.5), (14.5, 7.5),
    (23.5, 7.5), (28.5, 7.5), (9.5, 22.5), (14.5, 22.5),
]
FLOOR_H = 3.0

TEX = {  # char -> (RGB, glows at night)
    "W": ((235, 238, 248), False),
    "N": ((96, 122, 158), False),          # window glass: sky-tinted, visible
    "L": ((255, 214, 140), True),
    "R": ((96, 60, 40), False),
    "D": ((70, 50, 34), False),
    "S": ((190, 60, 60), False),
}


def detect_truecolor() -> bool:
    ct = os.environ.get("COLORTERM", "").lower()
    if "truecolor" in ct or "24bit" in ct:
        return True
    term = os.environ.get("TERM", "").lower()
    if any(n in term for n in ("kitty", "alacritty", "wezterm", "ghostty", "contour")):
        return True
    if os.environ.get("TERMINAL_EMULATOR", "").startswith("JetBrains"):
        return True
    return False


def rgb_to_256(rgb) -> int:
    r, g, b = rgb
    if r == g == b and 8 <= r <= 238 and (r - 8) % 10 == 0:
        return 232 + (r - 8) // 10
    return (16 + 36 * min(5, r * 6 // 256)
                + 6 * min(5, g * 6 // 256)
                + min(5, b * 6 // 256))


def mix(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def dayness(tod: float) -> float:
    return 0.5 - 0.5 * math.cos(2 * math.pi * tod)


# ---------------------------------------------------------------- geometry
def _quad(a, b, c, d, tex, rgb):
    """Two CCW triangles (seen from outside) with per-vertex texture chars."""
    return (
        (a, b, c, (tex[0], tex[1], tex[2]), rgb),
        (a, c, d, (tex[0], tex[2], tex[3]), rgb),
    )


# (dead first-draft builder removed; build_geometry_fixed is authoritative)


def build_geometry_fixed():
    tris = []
    for iy in range(H):
        for ix in range(W):
            ch = MAP[iy][ix]
            if ch not in LOT:
                continue
            stories, rgb = LOT[ch]
            h = stories * FLOOR_H
            x0, x1 = float(ix), float(ix + 1)
            y0, y1 = float(iy), float(iy + 1)
            seed = (ix * 31 + iy * 17) % 6
            shop = stories == 1 and seed % 2 == 0

            def band_rows(wseed):
                rows = []
                for s in range(stories):
                    if s == 0 and shop:
                        rows.append(["S", "D", "D", "S"])
                    else:
                        # window strip with wall piers between windows
                        rows.append([
                            "W" if k % 2 == 0 else
                            ("L" if (wseed * 7 + k * 5 + s * 3) % 3 == 0 else "N")
                            for k in range(4)])
                return rows

            walls = (
                ((x1, y0), (x1, y1), seed + 0),      # east, outward +x
                ((x1, y1), (x0, y1), seed + 1),      # south, outward +y
                ((x0, y1), (x0, y0), seed + 2),      # west, outward -x
                ((x0, y0), (x1, y0), seed + 3),      # north, outward -y
            )
            for (xa, ya), (xb, yb), wseed in walls:
                rows = band_rows(wseed)
                for s, row in enumerate(rows):
                    si = stories - 1 - s          # story 0 = TOP band (z high)
                    z0, z1 = si * FLOOR_H, (si + 1) * FLOOR_H
                    for k in range(4):
                        u0, u1 = k / 4, (k + 1) / 4
                        ax = xa + (xb - xa) * u0
                        ay = ya + (yb - ya) * u0
                        bx = xa + (xb - xa) * u1
                        by = ya + (yb - ya) * u1
                        t = row[k]
                        # window cells sit 2cm PROUD of the wall (along the
                        # outward normal, not along the wall!) so the
                        # z-buffer resolves them cleanly; shrunk 20% on each
                        # side so wall piers frame the window
                        off = 0.02 if t in "NL" else 0.0
                        wx, wy = xb - xa, yb - ya
                        ll = math.hypot(wx, wy) or 1.0
                        ox = -wy / ll * off              # outward normal
                        oy = wx / ll * off
                        shrink = 0.2 if t in "NL" else 0.0
                        w = xb - xa
                        h = yb - ya
                        ax2 = ax + w * shrink
                        ay2 = ay + h * shrink
                        bx2 = bx - w * shrink
                        by2 = by - h * shrink
                        # CCW seen from outside: (a,z0)->(b,z0)->(b,z1)->(a,z1)
                        tris += _quad((ax2 + ox, ay2 + oy, z0), (bx2 + ox, by2 + oy, z0),
                                      (bx2 + ox, by2 + oy, z1), (ax2 + ox, ay2 + oy, z1),
                                      (t, t, t, t), rgb)
            # roof: double-sided so it shades correctly from any angle
            tris += _quad((x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h),
                          ("R", "R", "R", "R"), rgb)
            tris += _quad((x1, y1, h), (x1, y0, h), (x0, y0, h), (x0, y1, h),
                          ("R", "R", "R", "R"), rgb)
    return tris


@dataclass
class Sprite:
    x: float
    y: float
    kind: str
    speed: float = 0.0
    color: tuple = (220, 60, 60)


@dataclass
class World:
    x: float = 10.5
    y: float = 16.5
    ang: float = 0.0            # in the long street, facing east down it
    pitch: float = 0.0
    weather: int = 0
    rain: bool = False
    tod: float = 0.35
    time_run: bool = True
    sprites: list = field(default_factory=list)
    t: float = 0.0


def make_world() -> World:
    cars = [
        Sprite(10.5, 6.8, "car", 2.6, (226, 70, 70)),
        Sprite(12.5, 15.4, "car", 3.1, (60, 210, 190)),
        Sprite(24.5, 7.4, "car", 2.3, (240, 190, 70)),
        Sprite(26.5, 12.2, "car", 2.9, (240, 90, 150)),
        Sprite(11.5, 8.6, "car", 2.5, (120, 130, 240)),
    ]
    people = [
        Sprite(3.5, 7.2, "person", 0.7, (120, 210, 255)),
        Sprite(20.5, 15.3, "person", 0.5, (255, 150, 200)),
        Sprite(33.5, 23.4, "person", 0.8, (180, 240, 120)),
        Sprite(9.5, 16.5, "person", 0.6, (255, 170, 90)),
        Sprite(28.5, 8.2, "person", 0.55, (230, 230, 140)),
    ]
    trees = [
        Sprite(2.6, 2.6, "tree"), Sprite(6.8, 2.9, "tree"),
        Sprite(2.4, 4.9, "tree"), Sprite(7.1, 4.6, "tree"),
        Sprite(4.9, 2.2, "tree"), Sprite(3.0, 5.3, "tree"),
    ]
    lamps = [Sprite(x, y, "lamp") for x, y in LAMPS]
    benches = [Sprite(3.2, 4.5, "bench"), Sprite(6.0, 4.5, "bench")]
    fountain = [Sprite(4.6, 3.6, "fountain")]
    birds = [
        Sprite(3.0, 6.5, "bird", -0.9),
        Sprite(20.0, 12.5, "bird", 0.7),
        Sprite(30.0, 21.0, "bird", -0.8),
    ]
    return World(sprites=cars + people + trees + lamps + benches + fountain + birds)


SPRITES = {  # kind -> (rows bottom->top, width)
    "car":    (" ███ ", "▄███▄", "▐█▌█▌"),   # 5 wide
    "person": ("█", "▓", "▄"),
    "tree":   ("▓█▓", "▒█▒", "░█░", " │ "),
    "lamp":   ("▀", "│", "│", "│"),
    "bench":  ("▬▬▬", " │ "),
    "fountain":("≈≈≈", "▒█▒", "▄▄▄"),
    "bird":   ("∧",),
}
SPRITE_W = {"car": 1.8, "person": 0.5, "tree": 1.5, "lamp": 0.25,
            "bench": 1.2, "fountain": 1.6, "bird": 0.6}
SPRITE_H = {"car": 1.4, "person": 1.7, "tree": 2.8, "lamp": 3.0,
            "bench": 0.6, "fountain": 1.4, "bird": 0.5}


def query_cell_pixels():
    try:
        import fcntl
        import struct
        import termios
        buf = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
        trows, tcols, xpix, ypix = struct.unpack("HHHH", buf)
        if xpix and ypix and tcols and trows:
            cw = max(2, round(xpix / tcols))
            ch = max(4, round(ypix / trows))
            if cw <= 64 and ch <= 128:
                return cw, ch
    except Exception:
        pass
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return 8, 16
    sys.stdout.write("\x1b[16t")
    sys.stdout.flush()
    ready, _, _ = select.select([sys.stdin], [], [], 0.08)
    if not ready:
        return 8, 16
    data = os.read(sys.stdin.fileno(), 64).decode("utf-8", "ignore")
    if not data.startswith("\x1b[6;") or not data.endswith("t"):
        return 8, 16
    parts = data[3:-1].split(";")
    if len(parts) != 2:
        return 8, 16
    try:
        height, width = int(parts[0]), int(parts[1])
    except ValueError:
        return 8, 16
    if width < 2 or height < 2:
        return 8, 16
    return width, height


def window_cells():
    cols, rows = os.get_terminal_size(sys.stdout.fileno() if sys.stdout.isatty() else 1)
    return max(20, cols), max(8, rows - 2)


# ------------------------------------------------------------- camera feed
def render(world: World, cols: int, rows: int, cell_w: int, cell_h: int):
    """Returns (chars, depth, attr) for painting. All screen math is done
    in terminal CELLS (cols/rows); cell_w/cell_h set the cell aspect used
    for the vertical focal length."""
    return _raster(world, cols, rows, cell_w, cell_h)


_TRIS = None


def _raster(world: World, cols: int, rows: int, cell_w: int, cell_h: int):
    """Full software raster of the city into (chars, depth), in cell space."""
    global _TRIS
    if _TRIS is None:
        chunks = {}
        for tri in build_geometry_fixed():
            cx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3
            cy = (tri[0][1] + tri[1][1] + tri[2][1]) / 3   # map-Y, not height
            key = (int(cx), int(cy))
            chunks.setdefault(key, []).append(tri)
        _TRIS = [(kx + 0.5, ky + 0.5, t) for (kx, ky), t in chunks.items()]
    fwd = (math.cos(world.ang), math.sin(world.ang))
    right = (-math.sin(world.ang), math.cos(world.ang))

    # Focal lengths measured in terminal CELLS so projection matches the
    # character-grid viewport exactly.
    focal_x = (cols / 2) / math.tan(FOV / 2)
    vfov = _cell_aspect(cell_w, cell_h)
    _VFOV[0] = vfov
    focal_y = focal_x * vfov
    half_w = cols / 2
    half_h = rows / 2
    pitch_off = world.pitch * focal_y * 0.6

    chars = [[" "] * cols for _ in range(rows)]
    depth = [[1e9] * cols for _ in range(rows)]
    attr = [[None] * cols for _ in range(rows)]

    # ---- buildings (per-lot chunks with cheap culling) --------------------
    cos_fov = math.cos(FOV * 0.75)
    cull_r2 = 34.0 * 34.0                 # fog hides everything past this
    ex0, ex1 = -world.x, -world.y
    fwd0, fwd1 = fwd
    right0, right1 = right
    for (ccx, ccy, tris) in _TRIS:
        ddx, ddy = ccx - world.x, ccy - world.y
        dist2 = ddx * ddx + ddy * ddy
        if dist2 > cull_r2:
            continue
        if dist2 > 25.0:                      # outside the view cone?
            if (ddx * fwd0 + ddy * fwd1) < cos_fov * math.sqrt(dist2):
                continue
        for (a, b, c, tex, rgb) in tris:
            t = tex[0]                        # sub-quads are single-texture
            # project vertices (camera space -> screen cells)
            v = []
            for (wx, wy, wz) in (a, b, c):
                dx, dy = wx + ex0, wy + ex1
                cz = dx * fwd0 + dy * fwd1
                if cz <= NEAR:
                    v = None
                    break
                v.append((half_w + ((dx * right0 + dy * right1) / cz) * focal_x,
                          half_h - ((wz - EYE) / cz) * focal_y + pitch_off,
                          cz))
            if not v:
                continue
            _raster_tri(v[0], v[1], v[2], t, chars, depth, attr, cols, rows, rgb)

    # ---- sprites (billboards) --------------------------------------------
    for sp in sorted(world.sprites,
                     key=lambda s: -((s.x - world.x) ** 2 + (s.y - world.y) ** 2)):
        _sprite(chars, depth, attr, cols, rows, world, focal_x, focal_y, half_w, half_h, sp)

    return chars, depth, attr


def _raster_tri(p0, p1, p2, t, chars, depth, attr, cols, rows, rgb):
    """Scanline fill with z-test. Back-face culls: building geometry is CCW
    seen from outside, which is a NEGATIVE shoelace area in y-down screen
    coords, so only negative areas are drawn."""
    area = ((p1[0] - p0[0]) * (p2[1] - p0[1])
            - (p2[0] - p0[0]) * (p1[1] - p0[1]))
    if area > -1e-9:                          # back-facing or degenerate
        return
    inv_area = 1.0 / area
    minx = max(0, int(min(p0[0], p1[0], p2[0])))
    maxx = min(cols - 1, int(max(p0[0], p1[0], p2[0])) + 1)
    miny = max(0, int(min(p0[1], p1[1], p2[1])))
    maxy = min(rows - 1, int(max(p0[1], p1[1], p2[1])) + 1)
    if minx > maxx or miny > maxy:
        return
    z0, z1, z2 = p0[2], p1[2], p2[2]
    dw0 = (p1[1] - p2[1]) * inv_area          # edge-function step per column
    dw1 = (p2[1] - p0[1]) * inv_area
    dz = dw0 * (z0 - z2) + dw1 * (z1 - z2)
    for r in range(miny, maxy + 1):
        py = r + 0.5
        drow = depth[r]
        crow = chars[r]
        arow = attr[r]
        px = minx + 0.5
        w0 = ((p1[0] - px) * (p2[1] - py)
              - (p2[0] - px) * (p1[1] - py)) * inv_area
        w1 = ((p2[0] - px) * (p0[1] - py)
              - (p0[0] - px) * (p2[1] - py)) * inv_area
        z = w0 * (z0 - z2) + w1 * (z1 - z2) + z2
        for c in range(minx, maxx + 1):
            if (w0 >= 0.0 and w1 >= 0.0 and w0 + w1 <= 1.0
                    and z < drow[c]):
                drow[c] = z
                crow[c] = t
                arow[c] = rgb
            w0 += dw0
            w1 += dw1
            z += dz


def _sprite(chars, depth, attr, cols, rows, world, focal_x, focal_y, half_w, half_h, sp):
    """Billboard sprite, drawn in terminal-cell space with per-cell colors."""
    dx, dy = sp.x - world.x, sp.y - world.y
    z = dx * math.cos(world.ang) + dy * math.sin(world.ang)
    if z < 0.6 or z > FAR:
        return
    xc = dx * -math.sin(world.ang) + dy * math.cos(world.ang)
    if abs(xc / z) > 2.5:                     # far outside the view frustum
        return
    art = SPRITES.get(sp.kind, ("█",))
    sw = SPRITE_W.get(sp.kind, 1.0)
    sh = SPRITE_H.get(sp.kind, 1.0)
    pitch_off = world.pitch * focal_y * 0.6
    cxc = half_w + (xc / z) * focal_x
    ground_c = half_h + (EYE / z) * focal_y + pitch_off
    art_cols = len(art[0])
    art_rows = len(art)
    cw_cells = (sw / z) * focal_x / art_cols
    rh_cells = (sh / z) * focal_y / art_rows
    # clamp: never let a near sprite grow past most of the screen
    max_h = rows * 0.85
    h_cells = rh_cells * art_rows
    if h_cells > max_h > 0:
        sc = max_h / h_cells
        cw_cells *= sc
        rh_cells *= sc
    rgb0 = sp.color
    for ar in range(art_rows):                # 0 = bottom row of the art
        rgb = (SPRITE_COLORS[sp.kind][ar]
               if ar < len(SPRITE_COLORS.get(sp.kind, ())) else rgb0)
        rr0 = int(round(ground_c - (ar + 1) * rh_cells))
        rr1 = int(round(ground_c - ar * rh_cells)) - 1
        for ac in range(art_cols):
            g = art[art_rows - 1 - ar][ac]    # art rows stored top->bottom
            if g == " ":
                continue
            cc0 = int(round(cxc - art_cols * cw_cells / 2 + ac * cw_cells))
            cc1 = int(round(cxc - art_cols * cw_cells / 2 + (ac + 1) * cw_cells)) - 1
            for r in range(max(0, rr0), min(rows, rr1 + 1)):
                for c in range(max(0, cc0), min(cols, cc1 + 1)):
                    if z <= depth[r][c]:
                        depth[r][c] = z
                        chars[r][c] = g
                        attr[r][c] = rgb


SPRITE_COLORS = {  # per art row, bottom -> top
    "tree":     ((118, 84, 52), (44, 118, 60), (54, 136, 68), (64, 150, 76)),
    "lamp":     ((70, 70, 78), (70, 70, 78), (70, 70, 78), (255, 214, 140)),
    "bench":    ((110, 78, 48), (128, 92, 58)),
    "fountain": ((150, 150, 158), (96, 148, 190), (172, 212, 232)),
    "bird":     ((60, 62, 70),),
}


def paint(world: World, chars, depth, attr, cols: int, rows: int):
    """chars+depth -> per-cell (char, fg, bg) with sky/ground/weather."""
    d = dayness(world.tod)
    night = 1.0 - d
    dusk = max(0.0, 1.0 - abs(d - 0.28) / 0.28)

    top = mix((6, 8, 20), (72, 124, 198), d)
    bot = mix((3, 4, 10), (158, 198, 240), d)
    if world.weather == 2:
        top, bot = mix(top, (58, 62, 72), 0.75), mix(bot, (70, 74, 82), 0.75)
    elif world.weather == 1:
        top, bot = mix(top, (50, 56, 66), 0.35), mix(bot, (60, 66, 76), 0.35)
    elif world.weather == 4:
        top, bot = mix(top, (150, 158, 172), 0.55), mix(bot, (185, 192, 205), 0.55)
    top = mix(top, (120, 60, 90), 0.35 * dusk)
    bot = mix(bot, (225, 120, 60), 0.55 * dusk)
    fogc = mix(top, bot, 0.45)

    def amb(c):
        return tuple(int(x * (1.0 - 0.30 * night)) for x in c)

    fwd = (math.cos(world.ang), math.sin(world.ang))
    focal_y = _focal(cols, rows) * _VFOV[0]
    horizon = rows * 0.5 + world.pitch * focal_y * 0.6
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            ch = chars[r][c]
            z = depth[r][c]
            if ch == " " or z >= 1e8:
                # sky above horizon, ground below
                if r < horizon:
                    t = r / max(1, rows - 1)
                    bg = (int(top[0] * (1 - t) + bot[0] * t),
                          int(top[1] * (1 - t) + bot[1] * t),
                          int(top[2] * (1 - t) + bot[2] * t))
                    row.append(("", None, bg))
                else:
                    bg = ground_bg(world, r, c, cols, rows, horizon, night, d)
                    row.append(("", None, bg))
                continue
            base = attr[r][c]
            if base is None:                       # sprite cell without color
                base = TEX.get(ch, ((200, 200, 200), False))[0]
            glow = TEX.get(ch, ((0, 0, 0), False))[1]
            k = 1.0 / (1.0 + z * 0.02)
            fogt = min(0.6, max(0.0, (z - 8) * 0.022))
            if glow and night > 0.2:
                colr = base
            else:
                colr = amb(base)
            colr = mix(mix(colr, (0, 0, 0), 1 - k), fogc, fogt)
            bg = mix(mix(amb(tuple(int(x * 0.55) for x in base)), (0, 0, 0), 1 - k), fogc, fogt)
            # texture code -> display glyph (codes are internal, never drawn)
            if ch == "W":
                g = ""                        # plain wall: facade color only
            elif ch == "N":
                g, bg = "░", amb((52, 64, 88))    # glassy window, not a void
            elif ch == "L":
                g, bg = "█", amb((70, 52, 28))
            elif ch == "R":
                g, bg = "▄", amb((70, 44, 30))
            elif ch == "D":
                g, bg = "▤", amb((60, 44, 30))
            elif ch == "S":
                g, bg = "▀", (255, 255, 255)
            else:
                g = ch
            row.append((g, colr, bg))
        out.append(row)
    return out


def ground_bg(world, r, c, cols, rows, horizon, night, d):
    """Ground color for an empty cell below the horizon: cast the cell's
    view ray onto the ground plane and sample the map block there."""
    focal_x = _focal(cols, rows)
    focal_y = focal_x * _VFOV[0]
    denom = (r + 0.5) - horizon
    dist = (EYE * focal_y) / denom if denom > 0.5 else 40.0
    # ray direction on the ground plane (screen x -> angle off forward)
    cam_x = (c + 0.5 - cols / 2) / focal_x
    ang2 = world.ang + math.atan(cam_x)
    mag = math.hypot(math.cos(ang2), math.sin(ang2)) or 1.0
    fx = world.x + math.cos(ang2) / mag * dist
    fy = world.y + math.sin(ang2) / mag * dist
    ix, iy = int(fx), int(fy)
    ch = MAP[iy][ix] if 0 <= iy < H and 0 <= ix < W else "3"
    def amb(x):
        return tuple(int(v * (1.0 - 0.30 * night)) for v in x)
    if ch == "+":
        bg = amb((152, 144, 128))          # sidewalk
    elif ch in ",;":
        bg = amb((58, 124, 66) if ch == "," else (50, 110, 60))
    else:
        bg = amb((92, 92, 102))            # asphalt street
        if abs((fx % 1) - 0.5) < 0.045 and int(fy * 2) % 2 == 0:
            bg = amb((235, 190, 80))       # dashed lane line
    # streetlight pools
    if night > 0.25 and ch in "+,":
        for lx, ly in LAMPS:
            ddx, ddy = fx - lx, fy - ly
            dd2 = ddx * ddx + ddy * ddy
            if dd2 < 1.2:
                bg = mix(bg, (255, 190, 110), 0.5)
                break
            if dd2 < 4.0:
                bg = mix(bg, (255, 190, 110), 0.15)
    k = 1.0 / (1.0 + dist * 0.05)
    return tuple(int(v * k) for v in bg)


_FOCAL_CACHE = [100.0]


def _focal(cols, rows):
    """Horizontal focal length in terminal cells (must match the raster)."""
    return (cols / 2) / math.tan(FOV / 2)


def to_ansi(buf, cols, rows, truecolor=True):
    if truecolor:
        def emit(ch, fg, bg):
            if ch:
                return f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]};48;2;{bg[0]};{bg[1]};{bg[2]}m"
            return f"\x1b[48;2;{bg[0]};{bg[1]};{bg[2]}m"
    else:
        cache = {}

        def q(rgb):
            i = cache.get(rgb)
            if i is None:
                i = rgb_to_256(rgb)
                cache[rgb] = i
            return i

        def emit(ch, fg, bg):
            if ch:
                return f"\x1b[38;5;{q(fg)};48;5;{q(bg)}m"
            return f"\x1b[48;5;{q(bg)}m"

    parts = []
    for row_index, row in enumerate(buf):
        # Address each row directly. Writing exactly `cols` cells can leave a
        # terminal in its pending-wrap state, so relying on CR/LF may scroll.
        parts.append(f"\x1b[{row_index + 1};1H")
        run = None
        n = 0
        for cell in row:
            if run == cell:
                n += 1
                continue
            if run is not None:
                ch, fg, bg = run
                parts.append(emit(ch, fg, bg) + (ch or " ") * n)
            run = cell
            n = 1
        if run is not None:
            ch, fg, bg = run
            parts.append(emit(ch, fg, bg) + (ch or " ") * n)
        parts.append("\x1b[0m")
    parts.append("\x1b[0m")
    return "".join(parts)


def to_ppm(buf, cell_w: int, cell_h: int, path: str) -> None:
    rows = len(buf)
    cols = len(buf[0]) if rows else 0
    with open(path, "wb") as f:
        f.write(f"P6\n{cols * cell_w} {rows * cell_h}\n255\n".encode())
        for row in buf:
            band = bytearray()
            for cell in row:
                band.extend((cell[2][0], cell[2][1], cell[2][2]) * cell_w)
            for _ in range(cell_h):
                f.write(band)


def step_world(world: World, dt: float, keys) -> None:
    world.t += dt
    if world.time_run:
        world.tod = (world.tod + dt / DAY_LEN) % 1.0
    sprint = any(k.isupper() for k in keys)
    speed = MOVE * (SPRINT if sprint else 1.0)
    strafe = 0.0
    if "a" in keys:
        strafe -= speed * dt
    if "d" in keys:
        strafe += speed * dt
    if "q" in keys:
        world.ang -= TURN * dt
    if "e" in keys:
        world.ang += TURN * dt
    fx, fy = math.cos(world.ang), math.sin(world.ang)
    move = 0.0
    if "w" in keys:
        move += speed * dt
    if "s" in keys:
        move -= speed * dt
    nx = world.x + fx * move
    ny = world.y + fy * move
    if not _solid_at(nx, world.y):
        world.x = nx
    if not _solid_at(world.x, ny):
        world.y = ny
    rx, ry = -fy, fx
    sx = world.x + rx * strafe
    sy = world.y + ry * strafe
    if not _solid_at(sx, world.y):
        world.x = sx
    if not _solid_at(world.x, sy):
        world.y = sy
    for sp in world.sprites:
        if sp.kind == "bird":
            sp.x += sp.speed * dt
            if sp.x > W - 2:
                sp.x = 2.0
            elif sp.x < 2:
                sp.x = W - 2.0
        elif sp.speed:
            sp.y += sp.speed * dt * (1.0 if sp.kind == "car" else 0.35)
            if sp.y > H - 2.5:
                sp.y = 5.8


def _solid_at(x: float, y: float) -> bool:
    for dx, dy in ((0.0, 0.0), (0.4, 0.0), (-0.4, 0.0),
                   (0.0, 0.4), (0.0, -0.4)):
        ix, iy = int(x + dx), int(y + dy)
        if ix < 0 or iy < 0 or ix >= W or iy >= H:
            return True
        if MAP[iy][ix] in LOT:
            return True
    return False


def play() -> None:
    import tty
    import termios
    import signal

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    truecolor = detect_truecolor()
    if "--256" in sys.argv:
        truecolor = False
    elif "--truecolor" in sys.argv:
        truecolor = True
    world = make_world()
    sens = 1.0
    mouse_look = True
    kitty = False
    keys = {}
    resized = True
    run = threading.Event()
    run.set()
    q = queue.Queue()

    def reader():
        while run.is_set():
            try:
                r, _, _ = select.select([fd], [], [], 0.05)
                if r:
                    q.put(os.read(fd, 256))
            except OSError:
                return

    def on_resize(*_a):
        nonlocal resized
        resized = True

    signal.signal(signal.SIGWINCH, on_resize)
    try:
        tty.setraw(fd)
        sys.stdout.write("\x1b[22;0t\x1b]2;Glyph City\x07\x1b[5t")
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1003h\x1b[?1006h\x1b[?1016h")
        sys.stdout.write("\x1b[>3u")
        sys.stdout.flush()
        cell_w, cell_h = query_cell_pixels()
        threading.Thread(target=reader, daemon=True).start()
        cols, rows = window_cells()
        last = time.perf_counter()
        mouse_prev = None
        mouse_px = False
        last_mouse_t = 0.0
        pend = b""
        while True:
            now = time.perf_counter()
            dt = min(0.08, now - last)
            last = now
            if resized:
                cols, rows = window_cells()
                cell_w, cell_h = query_cell_pixels()
                resized = False

            data = pend
            while True:
                try:
                    data += q.get_nowait()
                except queue.Empty:
                    break
            chunk = data.decode("utf-8", "ignore")
            i = 0
            incomplete = False
            quit_req = False
            while i < len(chunk):
                if chunk.startswith("\x1b[M", i):
                    if len(chunk) - i < 6:
                        incomplete = True
                        break
                    mouse_prev = None
                    i += 6
                    continue
                if chunk.startswith("\x1b[6;", i):
                    end = chunk.find("t", i)
                    i = end + 1 if end != -1 else len(chunk)
                    continue
                if chunk.startswith("\x1b[<", i):
                    end = chunk.find("M", i)
                    up = chunk.find("m", i)
                    stop = end if end != -1 and (up == -1 or end < up) else up
                    if stop == -1:
                        incomplete = True
                        break
                    body = chunk[i + 3: stop]
                    try:
                        btn, mx, my = (int(p) for p in body.split(";"))
                    except ValueError:
                        i = stop + 1
                        continue
                    px_mode = mx > cols or my > rows
                    if px_mode != mouse_px:
                        mouse_prev = None
                        mouse_px = px_mode
                    s = PX_SENS if px_mode else CELL_SENS
                    gap = now - last_mouse_t
                    if (mouse_look and mouse_prev is not None and gap < 0.35
                            and abs(mx - mouse_prev[0]) < 40
                            and abs(my - mouse_prev[1]) < 40):
                        world.ang += (mx - mouse_prev[0]) * s * sens
                        world.pitch = max(-0.6, min(0.6,
                            world.pitch - (my - mouse_prev[1]) * s * sens * 0.8))
                    mouse_prev = (mx, my)
                    last_mouse_t = now
                    i = stop + 1
                    continue
                if chunk.startswith("\x1b[", i) and i + 2 < len(chunk) and chunk[i + 2].isdigit():
                    j = i + 2
                    while j < len(chunk) and (chunk[j].isdigit() or chunk[j] in ";:"):
                        j += 1
                    if j >= len(chunk):
                        incomplete = True
                        break
                    if chunk[j] == "u" and j - i <= 32:
                        kitty = True
                        inner = chunk[i + 2: j]
                        seg = inner.split(";")
                        code = int(seg[0].split(":")[0])
                        mods, event = 1, 1
                        if len(seg) > 1:
                            m2 = seg[1].split(":")
                            mods = int(m2[0]) if m2[0] else 1
                            event = int(m2[1]) if len(m2) > 1 and m2[1] else 1
                        if code == 99 and mods & 4:
                            quit_req = True
                            i = j + 1
                            continue
                        key = chr(code).lower() if 65 <= code <= 122 else None
                        if key in "wasdqe":
                            if event == 3:
                                keys.pop(key, None)
                                keys.pop(key.upper(), None)
                            else:
                                keys[key.upper() if mods & 1 else key] = now
                        i = j + 1
                        continue
                if chunk.startswith("\x1b[A", i):
                    keys["w"] = now
                    i += 3
                    continue
                if chunk.startswith("\x1b[B", i):
                    keys["s"] = now
                    i += 3
                    continue
                if chunk.startswith("\x1b[D", i):
                    keys["q"] = now
                    i += 3
                    continue
                if chunk.startswith("\x1b[C", i):
                    keys["e"] = now
                    i += 3
                    continue
                ch = chunk[i]
                if ch == "\x03":
                    quit_req = True
                    i += 1
                    continue
                if ch in "wasdqe":
                    keys[ch] = now
                elif ch in "WASDQE":
                    keys[ch] = now
                elif ch == "n":
                    world.weather = (world.weather + 1) % 5
                    world.rain = world.weather in (1, 3)
                elif ch == "r":
                    world.rain = not world.rain
                elif ch == "c":
                    truecolor = not truecolor
                elif ch == "t":
                    world.time_run = not world.time_run
                elif ch == "y":
                    world.tod = (world.tod + 0.125) % 1.0
                elif ch == "m":
                    mouse_look = not mouse_look
                    mouse_prev = None
                elif ch in "-_":
                    sens = max(0.25, sens * 0.8)
                elif ch in "=+":
                    sens = min(4.0, sens * 1.25)
                i += 1
            pend = chunk[i:].encode("utf-8", "ignore") if incomplete else b""
            if quit_req:
                return
            cutoff = now - (4.0 if kitty else 0.30)
            stale = [k for k, ts in keys.items() if ts < cutoff]
            for k in stale:
                del keys[k]

            step_world(world, dt, keys)
            chars, depth, attr = render(world, cols, rows, cell_w, cell_h)
            buf = paint(world, chars, depth, attr, cols, rows)
            if world.rain and world.weather in (1, 3):
                drops = 90 if world.weather == 1 else 160
                for k in range(drops):
                    cc = (k * 47 + int(world.t * 40)) % cols
                    rr = (k * 19 + int(world.t * 30)) % rows
                    ch, fg, bg = buf[rr][cc]
                    buf[rr][cc] = ("╱" if (k + int(world.t * 20)) % 2 else "│",
                                   (170, 210, 230), bg)
            if world.weather == 4:
                for k in range(80):
                    cc = (k * 47 + int(world.t * 6 + 8 * math.sin(world.t + k))) % cols
                    rr = (k * 19 + int(world.t * 9)) % rows
                    ch, fg, bg = buf[rr][cc]
                    buf[rr][cc] = ("∙", (235, 240, 248), bg)
            sys.stdout.write("\x1b[?2026h" + to_ansi(buf, cols, rows, truecolor) + "\x1b[?2026l")
            clock = f"{int(world.tod * 24) % 24:02d}:{int((world.tod * 24 % 1) * 60):02d}"
            hud = (f" WASD move  Shift sprint  M-look {'on' if mouse_look else 'off'}  "
                   f"{WNAMES[world.weather]} {clock}  sens {sens:.1f}  "
                   f"{'TC' if truecolor else '256'} ")
            sys.stdout.write(f"\x1b[{rows + 1};1H\x1b[38;2;210;214;224;48;2;10;12;18m"
                             + hud[:cols] + "\x1b[0m")
            sys.stdout.flush()
            spent = time.perf_counter() - now
            if spent < 0.013:
                time.sleep(0.013 - spent)
    finally:
        run.clear()
        time.sleep(0.06)
        sys.stdout.write("\x1b[<u")
        sys.stdout.write("\x1b[?1016l\x1b[?1006l\x1b[?1003l\x1b[?1000l\x1b[?25h\x1b[?1049l\x1b[0m")
        sys.stdout.write("\x1b[23;0t")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def shot(cols: int = 100, rows: int = 32, cell_w: int = 8, cell_h: int = 16) -> str:
    world = make_world()
    world.tod = 0.5
    chars, depth, attr = render(world, cols, rows, cell_w, cell_h)
    buf = paint(world, chars, depth, attr, cols, rows)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot.ppm")
    to_ppm(buf, cell_w, cell_h, path)
    return path


if __name__ == "__main__":
    if "--shot" in sys.argv:
        print(shot())
    else:
        play()
