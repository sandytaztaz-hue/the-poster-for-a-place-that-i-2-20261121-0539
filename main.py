#!/usr/bin/env python3
"""VELDARA — where the aurora touches the rooftops.

A travel poster for a place that isn't there (make.fun bounty
the-poster-for-a-place-that-i-2-20261121-0539).

Pure Python 3.13 stdlib only (no PIL, no numpy, no network).
Renders a photographic-style 1024x1024 poster to /output/entry.png
(or $MAKEFUN_OUTPUT_DIR/entry.png) with a custom PNG writer.

Deterministic: fixed seed, two runs are byte-identical.
"""
import math
import os
import random
import struct
import sys
import zlib
from array import array

W = 1024
H = 1024
SEED = 20261121

rng = random.Random(SEED)

# ---------------------------------------------------------------- buffer
# Flat float buffer, 3 channels per pixel.
buf = array("f", bytes(4 * W * H * 3))


def _idx(x, y):
    return (y * W + x) * 3


def add_px(x, y, r, g, b, a=1.0):
    """Additive blend of a colour into pixel (x, y)."""
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] += r * a
        buf[i + 1] += g * a
        buf[i + 2] += b * a


def set_px(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] = r
        buf[i + 1] = g
        buf[i + 2] = b


def blend_px(x, y, r, g, b, a):
    """Alpha blend colour over pixel (x, y)."""
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        ia = 1.0 - a
        buf[i] = buf[i] * ia + r * a
        buf[i + 1] = buf[i + 1] * ia + g * a
        buf[i + 2] = buf[i + 2] * ia + b * a


def splat(cx, cy, rad, r, g, b, strength=1.0):
    """Soft radial glow spot centred at (cx, cy)."""
    r2 = rad * rad
    x0 = max(0, int(cx - rad))
    x1 = min(W - 1, int(cx + rad) + 1)
    y0 = max(0, int(cy - rad))
    y1 = min(H - 1, int(cy + rad) + 1)
    for y in range(y0, y1 + 1):
        dy = y - cy
        row = y * W
        for x in range(x0, x1 + 1):
            dx = x - cx
            d2 = dx * dx + dy * dy
            if d2 < r2:
                t = 1.0 - d2 / r2
                a = strength * t * t
                i = (row + x) * 3
                buf[i] += r * a
                buf[i + 1] += g * a
                buf[i + 2] += b * a


def fill_rect(x0, y0, x1, y1, r, g, b, a=1.0):
    x0 = max(0, int(x0))
    x1 = min(W - 1, int(x1))
    y0 = max(0, int(y0))
    y1 = min(H - 1, int(y1))
    for y in range(y0, y1 + 1):
        base = (y * W + x0) * 3
        for x in range(x0, x1 + 1):
            i = base + (x - x0) * 3
            if a >= 1.0:
                buf[i] = r
                buf[i + 1] = g
                buf[i + 2] = b
            else:
                ia = 1.0 - a
                buf[i] = buf[i] * ia + r * a
                buf[i + 1] = buf[i + 1] * ia + g * a
                buf[i + 2] = buf[i + 2] * ia + b * a


# ---------------------------------------------------------------- noise tile
# Precomputed fine grain tile (tiled over the image in the final pass).
TILE = 256
grain_tile = [[rng.gauss(0.0, 1.0) for _ in range(TILE)] for _ in range(TILE)]
# Coarse value-noise tile for texture (snow / rock / water).
COARSE = 128
coarse_tile = [[rng.random() for _ in range(COARSE)] for _ in range(COARSE)]


def coarse(x, y):
    """Smooth-ish pseudo-random value in [0, 1) from tiled noise."""
    cx = (x // 3) % COARSE
    cy = (y // 3) % COARSE
    a = coarse_tile[cy][cx]
    b = coarse_tile[cy][(cx + 1) % COARSE]
    c = coarse_tile[(cy + 1) % COARSE][cx]
    d = coarse_tile[(cy + 1) % COARSE][(cx + 1) % COARSE]
    fx = (x % 3) / 3.0
    fy = (y % 3) / 3.0
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


# ---------------------------------------------------------------- aurora model
# Three rippling curtains.  Per-x centre, amplitude and ray modulation.
AURORA_BANDS = []
for band in range(3):
    base_y = [150.0, 225.0, 300.0][band]
    amp_y = [46.0, 58.0, 40.0][band]
    width = [26.0, 34.0, 30.0][band]
    peak = [0.95, 0.80, 0.55][band]
    f1 = [0.011, 0.008, 0.013][band]
    f2 = [0.023, 0.017, 0.029][band]
    p1 = [0.7, 2.1, 4.0][band]
    p2 = [1.9, 0.4, 2.8][band]
    cy = []
    amp = []
    ray = []
    for x in range(W):
        cy.append(base_y + amp_y * math.sin(x * f1 + p1)
                  + 0.45 * amp_y * math.sin(x * f2 + p2))
        # Curtain fades toward the left and right edges.
        edge = math.sin(math.pi * (x + 40) / (W + 80)) ** 1.5
        amp.append(peak * (0.35 + 0.65 * edge))
        # Faint vertical rays.
        ray.append(0.72 + 0.28 * math.sin(x * 0.055 + p2 * 3.1)
                   * math.sin(x * 0.013 + p1))
    AURORA_BANDS.append((cy, amp, ray, width))

# Aurora strength per column (for the water reflection).
aurora_col = [0.0] * W
for x in range(W):
    s = 0.0
    for (cy, amp, ray, width) in AURORA_BANDS:
        s += amp[x] * ray[x]
    aurora_col[x] = s

SKY_BOTTOM = 452          # horizon
SHORE_Y = 632             # village shore / waterline
WATER_BOTTOM = 838        # foreground shore starts


# ---------------------------------------------------------------- pass 1: sky
def render_sky():
    exp = math.exp
    for y in range(0, SKY_BOTTOM):
        t = y / SKY_BOTTOM
        # Deep indigo at top -> dusky blue-violet at the horizon.
        sr = 7.0 + 26.0 * t * t
        sg = 10.0 + 30.0 * t * t
        sb = 30.0 + 62.0 * t
        row = y * W
        for x in range(W):
            r, g, b = sr, sg, sb
            for (cy, amp, ray, width) in AURORA_BANDS:
                dy = y - cy[x]
                ady = dy if dy >= 0 else -dy
                if ady < width * 3.0:
                    # Brighter along the lower edge of the curtain.
                    edge_boost = 1.0 + 0.55 * math.exp(-((dy - width * 0.9)
                                                        / (width * 0.55)) ** 2)
                    gg = exp(-(dy / width) ** 2) * amp[x] * ray[x] * edge_boost
                    if gg > 0.004:
                        # Green core, violet fringe.
                        core = gg
                        fringe = gg * (0.35 + 0.65 * min(1.0, ady / width))
                        r += 52.0 * fringe
                        g += 235.0 * core
                        b += 150.0 * core + 110.0 * fringe
            i = (row + x) * 3
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b


# ---------------------------------------------------------------- stars + moon
def render_stars():
    stars = []
    for _ in range(520):
        x = rng.randrange(0, W)
        y = rng.randrange(0, 430)
        # Fewer stars inside the bright aurora core.
        if aurora_col[x] > 1.1 and 120 < y < 360 and rng.random() < 0.55:
            continue
        mag = rng.random()
        stars.append((x, y, 0.35 + 0.65 * mag, 1 if mag < 0.82 else 2))
    for (x, y, bright, rad) in stars:
        v = 150.0 * bright + 60.0
        splat(x, y, rad + 1, v, v, v * 1.05, 0.85)
        set_px(x, y, min(255.0, v + 60.0), min(255.0, v + 60.0), 255.0)


def render_moon():
    mx, my, mr = 838, 118, 27
    # Halo.
    splat(mx, my, 95, 150, 160, 190, 0.30)
    splat(mx, my, 46, 210, 220, 240, 0.55)
    # Disc, then an offset shadow disc to make a crescent.
    for y in range(my - mr, my + mr + 1):
        for x in range(mx - mr, mx + mr + 1):
            dx = x - mx
            dy = y - my
            if dx * dx + dy * dy <= mr * mr:
                # Limb softening.
                d = math.sqrt(dx * dx + dy * dy) / mr
                glow = 235.0 - 55.0 * d
                # Crescent cut: shadow circle offset up-right.
                sx = x - (mx + 13)
                sy = y - (my - 9)
                if sx * sx + sy * sy > (mr - 2) * (mr - 2):
                    blend_px(x, y, glow, glow + 6, glow + 12, 0.96)


# ---------------------------------------------------------------- mountains
def ridge_y(x, base, a1, f1, p1, a2, f2, p2, dip_c, dip_w, dip_d):
    y = base + a1 * math.sin(x * f1 + p1) + a2 * math.sin(x * f2 + p2)
    d = (x - dip_c) / dip_w
    y += dip_d * math.exp(-d * d)   # fjord opening: ridge dips down
    return y


def render_mountains():
    # Ridge crests per column, with a fjord opening dipping at the centre.
    far_top = []
    near_top = []
    for x in range(W):
        far_top.append(int(ridge_y(x, 436, 30, 0.0042, 1.2, 16, 0.011, 0.5,
                                  512, 190, 26)))
        near_top.append(int(ridge_y(x, 482, 30, 0.0031, 2.0, 18, 0.0093, 0.9,
                                    512, 150, 34)))
    # Far ridge: pale, hazy blue-grey, filling down to the near ridge.
    for x in range(W):
        top = far_top[x]
        bottom = near_top[x] + 4
        for y in range(top, bottom):
            t = (y - top) / max(1, bottom - top)
            n = coarse(x, y)
            pn = coarse(x // 2, y // 2)   # large-scale patches
            # Lighter at the crest, darker toward the base (haze).
            r = 132.0 - 30.0 * t + (n - 0.5) * 10.0
            g = 146.0 - 30.0 * t + (n - 0.5) * 10.0
            b = 180.0 - 26.0 * t + (n - 0.5) * 10.0
            # Patchy snow near the crest, not a flat white band.
            if y - top < 6 + pn * 12 and pn > 0.52:
                r, g, b = 205.0, 216.0, 232.0
            # Soften the crest into the sky.
            if y - top < 12:
                f = 0.45 * (1.0 - (y - top) / 12.0)
                tt = y / SKY_BOTTOM
                sr = 7.0 + 26.0 * tt * tt
                sg = 10.0 + 30.0 * tt * tt
                sb = 30.0 + 62.0 * tt
                r = r * (1 - f) + sr * f
                g = g * (1 - f) + sg * f
                b = b * (1 - f) + sb * f
            set_px(x, y, r, g, b)
    # Near ridge: dark indigo with aurora-lit snow caps.
    for x in range(W):
        top = near_top[x]
        for y in range(top, SHORE_Y):
            t = (y - top) / 110.0
            if t > 1.0:
                t = 1.0
            n = coarse(x, y)
            pn = coarse(x // 2, y // 2)
            r = 30.0 + 16.0 * t + (n - 0.5) * 8.0
            g = 36.0 + 18.0 * t + (n - 0.5) * 8.0
            b = 62.0 + 22.0 * t + (n - 0.5) * 8.0
            # Faint aurora wash on the upper slope.
            if y - top < 40:
                glow = aurora_col[x] * 10.0 * (1.0 - (y - top) / 40.0)
                g += glow
                b += glow * 0.5
            # Snow cap catching green aurora light (patchy, close to crest).
            if y - top < 5 + pn * 7 and pn > 0.58:
                glow = aurora_col[x] * 26.0
                r = 168.0 + glow * 0.25
                g = 196.0 + glow
                b = 214.0 + glow * 0.45
            # Soften the crest into the far ridge behind it.
            if y - top < 6:
                f = 0.35 * (1.0 - (y - top) / 6.0)
                r = r * (1 - f) + 112.0 * f
                g = g * (1 - f) + 126.0 * f
                b = b * (1 - f) + 160.0 * f
            set_px(x, y, r, g, b)


# ---------------------------------------------------------------- village
WINDOWS = []   # (cx, cy) of lit windows, for water glints


def draw_house(x, w, body_h, roof_h, body, snow=True):
    """House with pitched snow roof; base y is SHORE_Y (ground line)."""
    top = SHORE_Y - body_h - roof_h
    # Body: dark timber with a faint vertical gradient.
    for y in range(top + roof_h, SHORE_Y):
        t = (y - top - roof_h) / max(1, body_h)
        n = coarse(x + w // 2, y)
        r = body[0] * (0.75 + 0.35 * t) + (n - 0.5) * 6
        g = body[1] * (0.75 + 0.35 * t) + (n - 0.5) * 6
        b = body[2] * (0.75 + 0.35 * t) + (n - 0.5) * 6
        fill_rect(x, y, x + w - 1, y, r, g, b)
    # Roof: triangle, snow-covered — apex at the top, eaves at the bottom.
    for dy in range(roof_h):
        y = top + dy
        half = (w / 2 + 4) * (dy / roof_h) + 1.5
        cx = x + w // 2
        n = coarse(cx, y)
        # Snow lit faintly green by the aurora on its upper face.
        glow = aurora_col[max(0, min(W - 1, cx))] * 14.0
        r = 178.0 + glow * 0.2 + (n - 0.5) * 12
        g = 192.0 + glow + (n - 0.5) * 12
        b = 212.0 + glow * 0.4 + (n - 0.5) * 12
        fill_rect(cx - half, y, cx + half, y, r, g, b)
    return top


def draw_window(wx, wy, ww=11, wh=15, lit=True):
    if lit:
        # Warm golden pane + bloom.
        splat(wx + ww // 2, wy + wh // 2, 16, 255, 176, 80, 0.45)
        splat(wx + ww // 2, wy + wh // 2, 8, 255, 200, 110, 0.7)
        fill_rect(wx, wy, wx + ww - 1, wy + wh - 1, 255, 196, 96)
        # Thin 1 px mullion cross (a 2 px cross read as a "+" sign).
        fill_rect(wx + ww // 2, wy, wx + ww // 2, wy + wh - 1, 60, 42, 20)
        fill_rect(wx, wy + wh // 2, wx + ww - 1, wy + wh // 2, 60, 42, 20)
        WINDOWS.append((wx + ww // 2, wy + wh // 2))
    else:
        fill_rect(wx, wy, wx + ww - 1, wy + wh - 1, 16, 20, 30)


def draw_church(x, w):
    """Church with a tall steeple, slightly right of centre — the focal point."""
    body_h, roof_h = 74, 30
    top = draw_house(x, w, body_h, roof_h, (52, 40, 34))
    # Steeple tower above the roof.
    tx = x + w // 2 - 9
    ty = top - 58
    fill_rect(tx, ty, tx + 18, top + 6, 46, 36, 32)
    # Spire (triangle): point at the top, widening to the tower.
    for dy in range(34):
        y = ty - 34 + dy
        half = 10 * (dy / 34.0) + 0.5
        cx = tx + 9
        fill_rect(cx - half, y, cx + half, y, 30, 26, 26)
    fill_rect(tx + 8, ty - 42, tx + 10, ty - 34, 220, 200, 150)
    fill_rect(tx + 5, ty - 39, tx + 13, ty - 37, 220, 200, 150)
    # Round lit window on the tower + arched door glow.
    splat(tx + 9, ty + 18, 12, 255, 190, 100, 0.7)
    fill_rect(tx + 5, ty + 13, tx + 13, ty + 23, 255, 200, 110)
    WINDOWS.append((tx + 9, ty + 18))
    # Body windows.
    draw_window(x + 8, SHORE_Y - 52, lit=True)
    draw_window(x + w - 18, SHORE_Y - 52, lit=True)
    draw_window(x + w // 2 - 5, SHORE_Y - 30, lit=False)


def render_village():
    bodies = [(58, 44, 34), (64, 48, 36), (52, 42, 36), (60, 46, 34),
              (56, 44, 38), (62, 46, 34), (54, 42, 34)]
    # (x, width, body_h, roof_h) — a loose row along the shore.
    houses = [
        (58, 74, 52, 26), (148, 88, 62, 30), (252, 66, 48, 24),
        (334, 82, 58, 28), (432, 70, 50, 25), (518, 78, 60, 28),
        (700, 84, 56, 27), (800, 72, 50, 25), (888, 76, 58, 29),
    ]
    # Dark shoreline strip so the houses sit on ground, not on the water.
    fill_rect(0, 618, W - 1, 640, 22, 24, 34)
    chimney_x = None
    for i, (x, w, bh, rh) in enumerate(houses):
        draw_house(x, w, bh, rh, bodies[i % len(bodies)])
        # Windows: 2-3 per house, most lit.
        nwin = 3 if w >= 78 else 2
        for k in range(nwin):
            if nwin > 1:
                wx = x + 8 + k * ((w - 28) // (nwin - 1))
            else:
                wx = x + w // 2 - 5
            lit = rng.random() < 0.82
            draw_window(wx, SHORE_Y - bh + 12, lit=lit)
        if i == 1:
            chimney_x = x + w - 14
            fill_rect(chimney_x, SHORE_Y - bh - rh - 6,
                      chimney_x + 9, SHORE_Y - bh - rh + 14, 40, 34, 30)
    # Church slightly right of centre.
    draw_church(606, 76)
    # Smoke curling from the chimney.
    if chimney_x:
        sx = chimney_x + 4
        sy = SHORE_Y - 62 - 30 - 6
        for s in range(9):
            cx = sx + int(10 * math.sin(s * 0.9)) + s * 4
            cy = sy - s * 13
            splat(cx, cy, 12 + s * 2, 190, 195, 210, 0.10)
            splat(cx, cy, 6 + s, 205, 208, 220, 0.08)


# ---------------------------------------------------------------- water
def render_water():
    # Window glint strength per column.
    glint = [0.0] * W
    for (wx, wy) in WINDOWS:
        for dx in range(-9, 10):
            xx = wx + dx
            if 0 <= xx < W:
                glint[xx] += math.exp(-(dx / 4.5) ** 2)
    for y in range(SHORE_Y, WATER_BOTTOM):
        t = (y - SHORE_Y) / (WATER_BOTTOM - SHORE_Y)
        # Dark blue-green water, deepening downward.
        br = 8.0 + 8.0 * t
        bg = 16.0 + 10.0 * t
        bb = 30.0 + 14.0 * t
        row = y * W
        wob = 6.0 * math.sin(y * 0.045)
        depth_fade = 1.0 - 0.55 * t   # reflections fade with depth
        ripple = 0.94 + 0.06 * math.sin(y * 0.22 + 0.005 * y)
        for x in range(W):
            xs = x + int(wob * math.sin(x * 0.012 + y * 0.02))
            xs = xs % W
            # Aurora reflection: broken, irregular vertical streaks.
            streak = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(xs * 0.31 + 1.7)
                                    * math.sin(xs * 0.083 + 0.4))
            streak *= 0.55 + 0.45 * coarse(xs // 6, y // 10)
            ar = aurora_col[xs] * depth_fade * ripple * streak
            r = br + 10.0 * ar
            g = bg + 46.0 * ar
            b = bb + 30.0 * ar
            # Warm window glints.
            gl = glint[xs] * depth_fade
            if gl > 0.02:
                flick = 0.75 + 0.25 * math.sin(y * 0.9 + xs * 0.3)
                r += 150.0 * gl * flick
                g += 105.0 * gl * flick
                b += 42.0 * gl * flick
            # Gentle texture.
            n = coarse(x, y)
            sh = (n - 0.5) * 4.0
            i = (row + x) * 3
            buf[i] = r + sh
            buf[i + 1] = g + sh
            buf[i + 2] = b + sh


# ---------------------------------------------------------------- foreground
def draw_pine(x, base_y, h, w):
    """Dark pine silhouette, snow-dusted on one edge."""
    layers = 4
    for li in range(layers):
        ly0 = base_y - h + li * (h // layers)
        ly1 = base_y - h + (li + 1) * (h // layers)
        half_max = w * (0.55 - 0.10 * li)
        for y in range(ly0, ly1):
            t = (y - ly0) / max(1, ly1 - ly0)
            half = half_max * (0.35 + 0.65 * t)
            cx = x
            for xx in range(int(cx - half), int(cx + half) + 1):
                if 0 <= xx < W:
                    n = coarse(xx, y)
                    r = 7.0 + (n - 0.5) * 4
                    g = 12.0 + (n - 0.5) * 4
                    b = 18.0 + (n - 0.5) * 4
                    # Snow dusting on the left edge of each bough.
                    if xx < cx - half + 3 and coarse(xx // 2, y // 2) > 0.55:
                        r, g, b = 150.0, 165.0, 185.0
                    set_px(xx, y, r, g, b)
    # Trunk.
    fill_rect(x - 2, base_y - 8, x + 2, base_y, 12, 10, 10)


def render_foreground():
    # Dark shoreline: rocks and snow-dusted ground sloping to the water.
    for y in range(WATER_BOTTOM, H):
        t = (y - WATER_BOTTOM) / (H - WATER_BOTTOM)
        for x in range(W):
            n = coarse(x, y)
            pn = coarse(x // 8, y // 8)   # large, soft snow patches
            # Ground: very dark blue-brown, slightly lighter toward the water.
            r = 16.0 + 10.0 * (1 - t) + (n - 0.5) * 6.0
            g = 19.0 + 10.0 * (1 - t) + (n - 0.5) * 6.0
            b = 30.0 + 12.0 * (1 - t) + (n - 0.5) * 6.0
            # Snow patches, softly blended in (no hard speckle).
            if pn > 0.60:
                s = min(1.0, (pn - 0.60) / 0.30) * 0.5
                r = r * (1 - s) + 125.0 * s
                g = g * (1 - s) + 138.0 * s
                b = b * (1 - s) + 160.0 * s
            set_px(x, y, r, g, b)
    # Boulders along the shore.
    for (cx, cy, rad) in [(180, 872, 34), (330, 902, 26), (700, 884, 30),
                          (880, 912, 38), (60, 940, 30), (960, 950, 28)]:
        for y in range(cy - rad, cy + rad + 1):
            for x in range(cx - rad, cx + rad + 1):
                dx = x - cx
                dy = (y - cy) * 1.6
                if dx * dx + dy * dy < rad * rad:
                    n = coarse(x, y)
                    top = 1.0 - (dy / rad if rad else 0)
                    r = 26.0 + 14.0 * top + (n - 0.5) * 10
                    g = 30.0 + 14.0 * top + (n - 0.5) * 10
                    b = 44.0 + 16.0 * top + (n - 0.5) * 10
                    if y < cy - rad * 0.45 and n > 0.45:
                        r, g, b = 165.0, 178.0, 198.0
                    set_px(x, y, r, g, b)
    # Pine silhouettes at the left edge.
    draw_pine(52, 1010, 150, 46)
    draw_pine(118, 1024, 190, 58)
    draw_pine(930, 1020, 130, 40)


# ---------------------------------------------------------------- typography
# Clean bold 5x7 bitmap font, A-Z.
FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
}


def text_width(text, scale, spacing):
    return len(text) * (5 * scale + spacing) - spacing


def draw_text(text, cx, y0, scale, spacing, color, glow=True):
    """Draw centred text; returns (x0, width)."""
    w = text_width(text, scale, spacing)
    x = cx - w // 2
    x0 = x
    # Soft warm halo behind the letters (helps legibility, keeps it photographic).
    if glow:
        for ch in text:
            glyph = FONT.get(ch)
            if glyph:
                for gy, row in enumerate(glyph):
                    for gx, bit in enumerate(row):
                        if bit == "1":
                            splat(x + gx * scale + scale // 2,
                                  y0 + gy * scale + scale // 2,
                                  scale * 1.1, 255, 205, 120, 0.10)
            x += 5 * scale + spacing
        x = x0
    # Crisp dark outline (drawn first, slightly offset in 4 directions).
    for (dx, dy) in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        xx = x0 + dx
        for ch in text:
            glyph = FONT.get(ch)
            if glyph:
                for gy, row in enumerate(glyph):
                    for gx, bit in enumerate(row):
                        if bit == "1":
                            fill_rect(xx + gx * scale, y0 + dy + gy * scale,
                                      xx + (gx + 1) * scale - 1,
                                      y0 + dy + (gy + 1) * scale - 1,
                                      8, 10, 18, a=0.85)
            xx += 5 * scale + spacing
    # Main letterforms.
    xx = x0
    for ch in text:
        glyph = FONT.get(ch)
        if glyph:
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        fill_rect(xx + gx * scale, y0 + gy * scale,
                                  xx + (gx + 1) * scale - 1,
                                  y0 + (gy + 1) * scale - 1,
                                  color[0], color[1], color[2])
        xx += 5 * scale + spacing
    return x0, w


def render_typography():
    # Subtle dark band behind the text (feathered, photographic, not a box).
    y0, y1 = 828, 1012
    for y in range(y0, y1):
        # Feather in/out over ~26 px.
        f = 1.0
        if y - y0 < 26:
            f = (y - y0) / 26.0
        if y1 - y < 26:
            f = min(f, (y1 - y) / 26.0)
        a = 0.52 * f
        row = y * W
        for x in range(140, 884):
            i = (row + x) * 3
            ia = 1.0 - a
            buf[i] *= ia
            buf[i + 1] *= ia
            buf[i + 2] *= ia
    cream = (246, 228, 178)
    gold = (212, 178, 110)
    # Thin gold rule above the name.
    for y in range(838, 841):
        for x in range(382, 643):
            blend_px(x, y, gold[0], gold[1], gold[2], 0.9)
    for y in range(841, 843):
        for x in range(382, 643):
            blend_px(x, y, gold[0], gold[1], gold[2], 0.35)
    draw_text("VELDARA", W // 2, 856, 14, 18, cream)
    # Thin gold rule below the tagline.
    draw_text("WHERE THE AURORA TOUCHES THE ROOFTOPS", W // 2, 972, 4, 4,
              (232, 214, 168), glow=False)
    for y in range(1006, 1008):
        for x in range(432, 593):
            blend_px(x, y, gold[0], gold[1], gold[2], 0.7)


# ---------------------------------------------------------------- PNG writer
def write_png(path, rows):
    """rows: list of bytes objects, one per scanline (RGB, no filter byte)."""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        c += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return c

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    raw = bytearray()
    prev = bytearray(W * 3)
    for row in rows:
        # Paeth filter.
        out = bytearray(W * 3)
        for i in range(W * 3):
            a = row[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            p = a + b - c
            pa = abs(p - a)
            pb = abs(p - b)
            pc = abs(p - c)
            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
            out[i] = (row[i] - pr) & 0xFF
        raw.append(4)
        raw.extend(out)
        prev = row
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


# ---------------------------------------------------------------- final pass
def render_final(out_path):
    rows = []
    cx, cy = W / 2.0, H / 2.0
    for y in range(H):
        vy = ((y - cy) / (H * 0.62)) ** 2
        row = bytearray(W * 3)
        base = y * W * 3
        gtile = grain_tile[y % TILE]
        for x in range(W):
            vx = ((x - cx) / (W * 0.62)) ** 2
            vig = 1.0 - 0.30 * min(1.0, (vx + vy) * 0.5)
            # Grain in 2x2 blocks: reads photographic, compresses far better.
            g = grain_tile[(y // 2) % TILE][(x // 2) % TILE] * 1.7
            i = base + x * 3
            r = buf[i] * vig + g
            gg = buf[i + 1] * vig + g
            b = buf[i + 2] * vig + g
            row[x * 3] = 0 if r < 0 else (255 if r > 255 else int(r))
            row[x * 3 + 1] = 0 if gg < 0 else (255 if gg > 255 else int(gg))
            row[x * 3 + 2] = 0 if b < 0 else (255 if b > 255 else int(b))
        rows.append(bytes(row))
    return write_png(out_path, rows)


# ---------------------------------------------------------------- main
def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")

    render_sky()
    render_stars()
    render_moon()
    render_mountains()
    render_village()
    render_water()
    render_foreground()
    render_typography()
    size = render_final(out_path)

    # Also write a local copy next to the repo when run locally, so the
    # entry can be inspected without the sandbox /output mount.
    local = os.path.join(os.getcwd(), "output", "entry.png")
    if os.path.abspath(out_path) != os.path.abspath(local):
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(out_path, "rb") as src, open(local, "wb") as dst:
            dst.write(src.read())

    print(f"wrote {out_path} ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
