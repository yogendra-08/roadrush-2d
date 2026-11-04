"""Procedural map generation: road layout data + rendered background + road mask.

The generated results are stored in ``assets/maps`` by ``tools/generate_assets.py``.
``game.map.GameMap`` also calls into this module as a fallback if any of those
files are missing, so the game can always rebuild its maps.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import procart
from .roadpath import RoadPath, catmull_rom_closed, resample_closed, smooth_closed

WORLD_W, WORLD_H = 3600, 2700
PATH_SPACING = 10.0
START_S = 90.0              # where the player starts (distance along the loop)
FINISH_FRACTION = 0.93      # finish line position as a fraction of the loop
CHECKPOINT_FRACTIONS = (0.17, 0.34, 0.50, 0.66, 0.80)

MAP_DEFS: dict[str, dict] = {
    "city": {
        "name": "City Map",
        "description": "Tight downtown streets lined with buildings, junction traffic and plenty of cones.",
        "theme": "city", "road_width": 200, "seed": 11,
        "lanes": [(-50, -1), (50, 1)],
        "obstacles": ["cone", "barrel", "crate", "tires", "barrier"],
        "control": [(0.16, 0.17), (0.40, 0.10), (0.62, 0.19), (0.88, 0.13), (0.91, 0.42), (0.70, 0.46),
                    (0.68, 0.64), (0.91, 0.72), (0.86, 0.91), (0.55, 0.86), (0.36, 0.92), (0.12, 0.86),
                    (0.10, 0.62), (0.28, 0.48), (0.20, 0.32)],
        "stars": 3,
    },
    "desert": {
        "name": "Desert Map",
        "description": "Long sweeping dunes and heat haze. Watch out for rocks and cactus on the blacktop.",
        "theme": "desert", "road_width": 190, "seed": 23,
        "lanes": [(-48, -1), (48, 1)],
        "obstacles": ["rock", "cactus", "barrel", "crate", "tires"],
        "control": [(0.10, 0.30), (0.30, 0.10), (0.55, 0.22), (0.80, 0.10), (0.92, 0.38), (0.75, 0.57),
                    (0.88, 0.80), (0.62, 0.91), (0.42, 0.74), (0.22, 0.91), (0.08, 0.68), (0.24, 0.50)],
        "stars": 2,
    },
    "forest": {
        "name": "Forest Map",
        "description": "A winding woodland road with fallen logs and rocks hiding around every bend.",
        "theme": "forest", "road_width": 180, "seed": 37,
        "lanes": [(-45, -1), (45, 1)],
        "obstacles": ["log", "rock", "crate", "cone", "barrel"],
        "control": [(0.14, 0.24), (0.35, 0.10), (0.50, 0.30), (0.66, 0.10), (0.87, 0.24), (0.80, 0.50),
                    (0.91, 0.76), (0.66, 0.90), (0.50, 0.70), (0.34, 0.90), (0.11, 0.78), (0.22, 0.52)],
        "stars": 3,
    },
    "highway": {
        "name": "Highway Map",
        "description": "A fast four-lane ring road. Wide curves, heavy traffic and roadworks barriers.",
        "theme": "highway", "road_width": 290, "seed": 53,
        "lanes": [(-105, -1), (-35, -1), (35, 1), (105, 1)],
        "obstacles": ["cone", "barrier", "barrel", "tires", "crate"],
        "control": [(0.10, 0.50), (0.17, 0.20), (0.50, 0.10), (0.83, 0.20), (0.91, 0.50), (0.83, 0.80),
                    (0.50, 0.90), (0.17, 0.80)],
        "stars": 1,
    },
}
MAP_ORDER = ("city", "desert", "forest", "highway")


# ============================================================ data / layout
def build_path(map_id: str) -> RoadPath:
    ctrl = [(x * WORLD_W, y * WORLD_H) for x, y in MAP_DEFS[map_id]["control"]]
    pts = resample_closed(catmull_rom_closed(ctrl), PATH_SPACING)
    hw, passes = MAP_DEFS[map_id].get("smooth", (14, 8))
    pts = smooth_closed(pts, hw, passes)
    return RoadPath(resample_closed(pts, PATH_SPACING))


def build_map_data(map_id: str) -> dict:
    """Pure-data description of a map (JSON serialisable)."""
    mdef = MAP_DEFS[map_id]
    path = build_path(map_id)
    rng = random.Random(mdef["seed"])
    L = path.length
    width = mdef["road_width"]

    finish_s = FINISH_FRACTION * L
    gates = [f * L for f in CHECKPOINT_FRACTIONS]

    def pose(s, lateral=0.0):
        x, y = path.offset_pos(s, lateral)
        return {"x": round(x, 1), "y": round(y, 1), "heading": round(path.heading_at(s), 2), "s": round(s, 1)}

    lane_offsets = [o for o, _ in mdef["lanes"]]
    start = pose(START_S, min(o for o in lane_offsets if o > 0))

    def near_gate(s, margin):
        return any(abs(s - g) < margin for g in gates + [finish_s, START_S])

    # --- coins: short lines, sometimes weaving
    coins = []
    s = 400.0
    while s < finish_s - 250:
        lat = rng.choice(lane_offsets) * rng.uniform(0.4, 1.2)
        weave = rng.choice([0, 0, 14])
        for k in range(rng.randint(4, 7)):
            ss = s + k * 55
            if near_gate(ss, 70):
                continue
            x, y = path.offset_pos(ss, lat + math.sin(k * 0.9) * weave)
            coins.append({"x": round(x, 1), "y": round(y, 1)})
        s += rng.uniform(380, 640)

    # --- fuel cans spaced evenly
    fuel = []
    for k in range(8):
        ss = finish_s * (k + 0.55) / 8
        x, y = path.offset_pos(ss, rng.uniform(-0.3, 0.3) * width)
        fuel.append({"x": round(x, 1), "y": round(y, 1)})

    # --- obstacles (priority 'p' lets difficulty pick a subset deterministically)
    obstacles = []
    last_s = 0.0
    s = 650.0
    types = mdef["obstacles"]
    while s < finish_s - 150:
        s += rng.uniform(110, 270)
        if near_gate(s, 120) or s - last_s < 100:
            continue
        kind = rng.choice(types)
        spread = 0.27 if kind in ("barrier", "log") else 0.36
        lat = rng.uniform(-spread, spread) * width
        heading = path.heading_at(s)
        if kind in ("cone", "barrel"):
            rot = 0.0
        elif kind == "barrier":
            rot = heading + rng.choice([0, 0, 90])
        elif kind == "log":
            rot = heading + rng.uniform(-35, 35)
        else:
            rot = rng.uniform(0, 360)
        prio = round(rng.random(), 3)
        x, y = path.offset_pos(s, lat)
        obstacles.append({"t": kind, "x": round(x, 1), "y": round(y, 1), "rot": round(rot, 1), "p": prio})
        if kind in ("cone", "barrel") and rng.random() < 0.35:       # little clusters
            for j in (1, 2):
                x2, y2 = path.offset_pos(s + j * 34, lat + j * rng.choice([-1, 1]) * 20)
                obstacles.append({"t": kind, "x": round(x2, 1), "y": round(y2, 1), "rot": 0.0, "p": prio})
        last_s = s

    return {
        "id": map_id,
        "name": mdef["name"],
        "description": mdef["description"],
        "theme": mdef["theme"],
        "stars": mdef["stars"],
        "world": [WORLD_W, WORLD_H],
        "road_width": width,
        "lanes": [list(l) for l in mdef["lanes"]],
        "path": [[round(x, 1), round(y, 1)] for x, y in path.points],
        "start": start,
        "finish": pose(finish_s),
        "checkpoints": [pose(g) for g in gates],
        "coins": coins,
        "fuel": fuel,
        "obstacles": obstacles,
    }


# ============================================================ rendering
_THEME = {
    "city": dict(ground=((84, 88, 96), (118, 122, 132)), shoulder=(168, 170, 176), asphalt=((54, 56, 62), (74, 76, 84))),
    "desert": dict(ground=((206, 168, 102), (236, 200, 134)), shoulder=(214, 184, 130), asphalt=((62, 58, 58), (84, 78, 76))),
    "forest": dict(ground=((36, 96, 46), (66, 138, 70)), shoulder=(118, 94, 62), asphalt=((58, 58, 64), (78, 78, 86))),
    "highway": dict(ground=((92, 156, 68), (126, 188, 92)), shoulder=(150, 144, 128), asphalt=((44, 46, 52), (64, 66, 74))),
}


def _noise_texture(size, scale, sigma, c_dark, c_light) -> Image.Image:
    w, h = size
    small = Image.effect_noise((max(2, w // scale), max(2, h // scale)), sigma)
    gray = small.resize(size, Image.BICUBIC)
    return ImageOps.colorize(ImageOps.autocontrast(gray, cutoff=2), c_dark, c_light).convert("RGB")


def _disc_mask(path: RoadPath, radius: float, size=(WORLD_W, WORLD_H), step=2) -> Image.Image:
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for i in range(0, path.n, step):
        x, y = path.points[i]
        d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=255)
    return m


def _offset_line(path: RoadPath, lateral: float, i0=0, i1=None):
    i1 = path.n if i1 is None else i1
    pts = []
    for i in range(i0, i1 + 1):
        j = i % path.n
        h = math.radians(path.headings[j])
        pts.append((path.xs[j] + math.cos(h) * lateral, path.ys[j] + math.sin(h) * lateral))
    return pts


def _dashes(d, path, lateral, color, width, dash=6, gap=5):
    i = 0
    while i < path.n:
        d.line(_offset_line(path, lateral, i, min(i + dash, path.n)), fill=color, width=width)
        i += dash + gap


def _strip(d, path, s, along, lateral_from, lateral_to, color):
    pts = [path.offset_pos(s, lateral_from), path.offset_pos(s, lateral_to),
           path.offset_pos(s + along, lateral_to), path.offset_pos(s + along, lateral_from)]
    d.polygon(pts, fill=color)


def _checker(d, path, s, width):
    cell = 20
    cols = int(width // cell)
    for row in range(2):
        for col in range(cols):
            color = (250, 250, 250) if (row + col) % 2 == 0 else (24, 24, 24)
            lf = -width / 2 + col * cell + (width - cols * cell) / 2
            _strip(d, path, s + row * cell, cell, lf, lf + cell, color)


def _clear(keepout: bytes, x: float, y: float, r: float) -> bool:
    for dx, dy in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r)):
        px, py = int(x + dx), int(y + dy)
        if not (0 <= px < WORLD_W and 0 <= py < WORLD_H):
            continue
        if keepout[py * WORLD_W + px]:
            return False
    return True


def _tree(d, x, y, r, rng, palette):
    d.ellipse([x - r + 8, y - r + 10, x + r + 8, y + r + 10], fill=palette[0])
    for k in range(3):
        ox, oy = rng.uniform(-r * 0.25, r * 0.25), rng.uniform(-r * 0.25, r * 0.25)
        rr = r * (1 - 0.18 * k)
        d.ellipse([x + ox - rr, y + oy - rr, x + ox + rr, y + oy + rr], fill=palette[1 + k])
    d.ellipse([x - r * 0.3 - 4, y - r * 0.35 - 4, x - r * 0.3 + 6, y - r * 0.35 + 6], fill=palette[4])


def _paste_sprite(bg, sprite, x, y, rot):
    img = sprite.rotate(-rot, expand=True, resample=Image.BICUBIC)
    bg.paste(img, (int(x - img.width / 2), int(y - img.height / 2)), img)


def render_map_images(data: dict, progress=None) -> tuple[Image.Image, Image.Image]:
    """Render ``(background RGB image, road mask 'L' image)`` for a map description."""
    theme = data["theme"]
    th = _THEME[theme]
    path = RoadPath([tuple(p) for p in data["path"]])
    width = data["road_width"]
    size = (WORLD_W, WORLD_H)
    rng = random.Random(MAP_DEFS[data["id"]]["seed"] * 7 + 1)

    def tick(msg):
        if progress:
            progress(msg)

    tick("road masks")
    road_mask = _disc_mask(path, width / 2)
    shoulder_mask = _disc_mask(path, width / 2 + 24)
    keepout = _disc_mask(path, width / 2 + 34).tobytes()

    tick("terrain")
    bg = _noise_texture(size, 7 if theme in ("forest", "highway") else 10, 40, *th["ground"])
    if theme == "desert":   # long streaky dunes
        dunes = Image.effect_noise((WORLD_W // 160, WORLD_H // 12), 60).resize(size, Image.BICUBIC)
        dunes = ImageOps.colorize(ImageOps.autocontrast(dunes, cutoff=2), (176, 132, 76), (240, 206, 140)).convert("RGB")
        bg = Image.blend(bg, dunes, 0.45)
    d = ImageDraw.Draw(bg)

    tick("scenery")
    if theme == "city":
        lot = 120
        palettes = [(150, 140, 126), (126, 134, 150), (160, 154, 146), (112, 118, 128), (176, 120, 100),
                    (110, 130, 120), (170, 166, 120), (96, 102, 120)]
        for gx in range(0, WORLD_W, lot):
            for gy in range(0, WORLD_H, lot):
                cx, cy = gx + lot / 2, gy + lot / 2
                if not _clear(keepout, cx, cy, lot * 0.62):
                    continue
                roll = rng.random()
                if roll < 0.10:                                  # small park
                    d.rectangle([gx + 8, gy + 8, gx + lot - 8, gy + lot - 8], fill=(70, 128, 70))
                    for _ in range(3):
                        _tree(d, gx + rng.randint(26, lot - 26), gy + rng.randint(26, lot - 26), 20, rng,
                              [(50, 98, 54), (44, 112, 52), (56, 130, 62), (70, 148, 74), (110, 180, 110)])
                    continue
                if roll < 0.16:
                    continue                                      # empty plaza
                bw, bh = rng.randint(76, 108), rng.randint(76, 108)
                bx = gx + (lot - bw) / 2 + rng.randint(-5, 5)
                by = gy + (lot - bh) / 2 + rng.randint(-5, 5)
                col = rng.choice(palettes)
                d.rectangle([bx + 12, by + 12, bx + bw + 12, by + bh + 12], fill=(54, 56, 62))
                d.rectangle([bx, by, bx + bw, by + bh], fill=tuple(int(c * 0.78) for c in col))
                d.rectangle([bx + 5, by + 5, bx + bw - 5, by + bh - 5], fill=col)
                d.rectangle([bx + 12, by + 12, bx + 12 + rng.randint(14, 26), by + 12 + rng.randint(12, 22)],
                            fill=tuple(int(c * 0.88) for c in col))
                d.line([(bx + 5, by + bh // 2), (bx + bw - 5, by + bh // 2)], fill=tuple(int(c * 0.86) for c in col), width=2)
    elif theme == "desert":
        rocks = [procart.make_obstacle("rock", k) for k in range(4)]
        cacti = [procart.make_obstacle("cactus", 0)]
        for _ in range(520):
            x, y = rng.uniform(0, WORLD_W), rng.uniform(0, WORLD_H)
            if _clear(keepout, x, y, 40):
                spr = rng.choice(rocks if rng.random() < 0.6 else cacti)
                scale = rng.uniform(0.8, 2.2) if spr in rocks else rng.uniform(0.9, 1.5)
                spr = spr.resize((int(spr.width * scale), int(spr.height * scale)), Image.LANCZOS)
                _paste_sprite(bg, spr, x, y, rng.uniform(0, 360))
        for _ in range(900):                                        # dry scrub dots
            x, y = rng.uniform(0, WORLD_W), rng.uniform(0, WORLD_H)
            if _clear(keepout, x, y, 14):
                for _k in range(4):
                    ox, oy = rng.uniform(-8, 8), rng.uniform(-8, 8)
                    d.ellipse([x + ox - 4, y + oy - 4, x + ox + 4, y + oy + 4], fill=(150, 124, 66))
    elif theme == "forest":
        pal_a = [(20, 60, 30), (28, 84, 40), (36, 104, 48), (48, 124, 58), (110, 176, 100)]
        pal_b = [(22, 68, 34), (34, 96, 46), (46, 118, 54), (60, 140, 66), (122, 190, 108)]
        for _ in range(2700):
            x, y = rng.uniform(0, WORLD_W), rng.uniform(0, WORLD_H)
            r = rng.uniform(26, 56)
            if _clear(keepout, x, y, r):
                _tree(d, x, y, r, rng, rng.choice([pal_a, pal_b]))
        for _ in range(4):                                          # ponds
            px, py = rng.uniform(300, WORLD_W - 300), rng.uniform(300, WORLD_H - 300)
            if _clear(keepout, px, py, 140):
                d.ellipse([px - 120, py - 80, px + 120, py + 80], fill=(70, 100, 70))
                d.ellipse([px - 110, py - 70, px + 110, py + 70], fill=(52, 120, 168))
                d.ellipse([px - 70, py - 40, px + 40, py + 20], fill=(86, 148, 192))
    elif theme == "highway":
        for _ in range(130):                                        # farm fields
            fx, fy = rng.uniform(0, WORLD_W), rng.uniform(0, WORLD_H)
            fw, fh = rng.uniform(200, 520), rng.uniform(160, 380)
            tint = rng.choice([(176, 190, 84), (140, 180, 78), (204, 188, 96), (106, 164, 76)])
            for k in range(0, int(fh), 14):
                shade = 0.92 if (k // 14) % 2 else 1.0
                if _clear(keepout, fx + fw / 2, fy + k, 10) and _clear(keepout, fx, fy + k, 10) and _clear(keepout, fx + fw, fy + k, 10):
                    d.rectangle([fx, fy + k, fx + fw, fy + k + 12], fill=tuple(int(c * shade) for c in tint))
        pal = [(30, 84, 40), (38, 106, 48), (50, 128, 58), (64, 148, 70), (126, 196, 116)]
        for _ in range(420):
            x, y = rng.uniform(0, WORLD_W), rng.uniform(0, WORLD_H)
            r = rng.uniform(18, 34)
            if _clear(keepout, x, y, r):
                _tree(d, x, y, r, rng, pal)

    tick("road surface")
    shoulder = Image.new("RGB", size, th["shoulder"])
    bg.paste(shoulder, (0, 0), shoulder_mask.filter(ImageFilter.GaussianBlur(1.5)))
    asphalt = _noise_texture(size, 3, 30, *th["asphalt"])
    bg.paste(asphalt, (0, 0), road_mask.filter(ImageFilter.GaussianBlur(1.2)))
    d = ImageDraw.Draw(bg)

    tick("markings")
    white, yellow = (236, 236, 232), (240, 196, 40)
    edge = width / 2 - 12
    for sgn in (-1, 1):
        d.line(_offset_line(path, sgn * edge, 0, path.n), fill=white, width=6, joint="curve")
    offsets = sorted(o for o, _ in data["lanes"])
    if len(offsets) == 2:
        _dashes(d, path, 0, yellow, 5, 7, 6)
    else:
        for sgn in (-4, 4):
            d.line(_offset_line(path, sgn, 0, path.n), fill=yellow, width=4, joint="curve")
        for o in (-70, 70):
            _dashes(d, path, o, white, 4, 7, 7)
    if theme == "city":                                            # zebra crossings
        s = 1500.0
        while s < path.length - 1200:
            for k in range(-4, 5):
                _strip(d, path, s, 26, -width / 2 + 16 + (k + 4) * (width - 32) / 9,
                       -width / 2 + 16 + (k + 4) * (width - 32) / 9 + (width - 32) / 18, white)
            s += 2300
    elif theme == "highway":                                       # rumble edge
        for sgn in (-1, 1):
            _dashes(d, path, sgn * (width / 2 - 4), (214, 54, 46), 6, 3, 3)

    # start grid + finish line
    s0 = data["start"]["s"]
    _checker(d, path, s0 - 56, width - 24)
    fin = data["finish"]["s"]
    _checker(d, path, fin, width - 24)
    for cp in data["checkpoints"]:       # faint painted line under every gate
        _strip(d, path, cp["s"], 6, -width / 2 + 10, width / 2 - 10, (255, 210, 60))
    return bg, road_mask
