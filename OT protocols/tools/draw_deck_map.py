"""Draws maps/deck_map.svg (OT-2 deck for sdl_solubility_ot2.py). The committed SVG was finished by hand in
Illustrator; this script draws the same content, so re-running it replaces those hand edits. Static drawing: update
the slot assignments below if you move labware in the protocol, then re-run:

    python tools/draw_deck_map.py
"""
import importlib.util
import os
import sys
from pathlib import Path

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "maps", "deck_map.svg")
_spec = importlib.util.spec_from_file_location("production_config", Path(__file__).resolve().parents[2] / "production" / "config.py")
cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cfg)
# matplotlib "bone" (greys) + "twilight" (accents)
INK, DARK, MID, LIGHT, PALE, BG = "#16161e", "#42425d", "#707b90", "#b9d2d2", "#dde9e9", "#eff4f4"
TW = ["#e2d9e2", "#a6bfca", "#6d90c0", "#5f58b0", "#531e7c", "#64194b", "#9f3c50", "#c0755e", "#d0b39e"]
SW, SH, GAP = 190, 128, 10
X0, Y0 = 1, 79
GRID = [["10", "11", "12"], ["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"]]
out = []
add = out.append

def xy(slot):
    for r, row in enumerate(GRID):
        if slot in row:
            return X0 + row.index(slot) * (SW + GAP), Y0 + r * (SH + GAP)

def label(slot, text, sub):
    x, y = xy(slot)
    add(f'<text x="{x+SW/2}" y="{y+SH-20}" text-anchor="middle" font-size="12" font-weight="bold" fill="{INK}">{text}</text>')
    add(f'<text x="{x+SW/2}" y="{y+SH-6}" text-anchor="middle" font-size="9.5" fill="{MID}">{sub}</text>')

def frame(slot, fill, stroke, w=150, h=82, rx=6):
    x, y = xy(slot)
    bx, by = x + (SW - w) / 2, y + 10
    add(f'<rect x="{bx}" y="{by}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
    return bx, by, w, h

def wells(bx, by, w, h, r, fill, stroke, pad=9):
    dx, dy = (w - 2 * pad) / 11, (h - 2 * pad) / 7
    for i in range(12):
        for j in range(8):
            add(f'<circle cx="{bx+pad+i*dx:.1f}" cy="{by+pad+j*dy:.1f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>')

def plate(slot, n):
    bx, by, w, h = frame(slot, "#ffffff", DARK)
    wells(bx, by, w, h, 3.0, "#ffffff", MID)
    label(slot, f"Readout plate {n} (solids)", "sarstedt_96_wellplate_390ul_flat")

def blank_plate(slot):
    """96-well plate with one well of each pure solvent: well X1 = trough X1, no solids."""
    bx, by, w, h = frame(slot, "#ffffff", DARK)
    pad = 9
    dx, dy = (w - 2 * pad) / 11, (h - 2 * pad) / 7
    by_trough = {t[0]: cfg.SOLVENT_LABELS[name] for name, t in cfg.SOLVENT_TROUGHS.items()}
    rows = [r for r in "ABCDEFGH" if f"{r}1" in by_trough]
    cols = [TW[2], TW[3], TW[4], TW[5], TW[6], TW[7], TW[8], LIGHT]
    for i in range(12):
        for j in range(8):
            cx, cy = bx + pad + i * dx, by + pad + j * dy
            if i == 0 and "ABCDEFGH"[j] in rows:
                add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" fill="{cols[j]}" stroke="{INK}" stroke-width="0.8"/>')
            else:
                add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.0" fill="#ffffff" stroke="{MID}" stroke-width="0.8"/>')
    # name panel over columns 2-5 (empty wells), one line per filled row
    add(f'<rect x="{bx+pad+dx-4:.1f}" y="{by+3}" width="{4*dx+4:.1f}" height="{7*dy+2:.1f}" rx="3" fill="#ffffff" stroke="{PALE}"/>')
    for r in rows:
        j = "ABCDEFGH".index(r)
        add(f'<text x="{bx+pad+dx:.1f}" y="{by+pad+j*dy+2.6:.1f}" font-size="7.5" fill="{INK}">{r}1 {by_trough[r + "1"]}</text>')
    label(slot, "Solvent blank plate", f"{cfg.TOTAL_UL} µL, no solids")


def tips(slot, size, rack):
    bx, by, w, h = frame(slot, PALE, MID)
    wells(bx, by, w, h, 2.6 if size == "20" else 3.1, "#ffffff", MID)
    label(slot, f"{size} µL tips", rack)

def reservoir(slot, title="Solvent reservoir", sub="axygen_8_reservoir_30000ul"):
    bx, by, w, h = frame(slot, "#ffffff", DARK)
    # trough A1..H1 from production/config.toml; any trough without a solvent is the diluent
    by_trough = {t[0]: cfg.SOLVENT_LABELS[name] for name, t in cfg.SOLVENT_TROUGHS.items()}
    names = [by_trough.get(f"{r}1", "") for r in "ABCDEFGH"]  # unused troughs (H1 diluent) stay unlabelled
    cols = [TW[2], TW[3], TW[4], TW[5], TW[6], TW[7], TW[8], LIGHT]
    bh = (h - 10) / 8
    for i in range(8):
        add(f'<rect x="{bx+6}" y="{by+5+i*bh:.1f}" width="{w-12}" height="{bh-1.6:.1f}" rx="2" fill="{cols[i]}" fill-opacity="0.85"/>')
        txt = "#ffffff" if 1 <= i <= 6 else INK
        if names[i]:
            add(f'<text x="{bx+w/2}" y="{by+5+i*bh+bh/2+2.8:.1f}" text-anchor="middle" font-size="7.5" fill="{txt}">{"ABCDEFGH"[i]}1 {names[i]}</text>')
    label(slot, title, sub)

def heater_shaker(slot):
    x, y = xy(slot)
    add(f'<rect x="{x+12}" y="{y+6}" width="{SW-24}" height="{SH-36}" rx="9" fill="{DARK}"/>')
    add(f'<rect x="{x+26}" y="{y+14}" width="{SW-52}" height="{SH-52}" rx="4" fill="{LIGHT}" stroke="{INK}"/>')
    add(f'<text x="{x+SW/2}" y="{y+SH/2-10}" text-anchor="middle" font-size="9.5" fill="{INK}">universal flat adapter</text>')
    add(f'<text x="{x+SW/2}" y="{y+SH/2+4}" text-anchor="middle" font-size="9" fill="{INK}">plates moved here by hand</text>')
    label(slot, "Heater-shaker GEN1", "heaterShakerModuleV1")

W = X0 + 3 * (SW + GAP) - GAP + 1
H = Y0 + 4 * (SH + GAP) - GAP + 1
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Arial">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
add(f'<text x="{X0}" y="17" font-size="20" font-weight="bold" fill="{INK}">OT-2 deck map: to run sdl_solubility_ot2.py</text>')
add(f'<text x="{X0}" y="39" font-size="12" fill="{MID}">P300 GEN2 single (left) · P20 GEN2 single (right)</text>')
for row in GRID:
    for s in row:
        x, y = xy(s)
        add(f'<rect x="{x}" y="{y}" width="{SW}" height="{SH}" rx="6" fill="{BG}" stroke="{PALE}" stroke-width="2"/>')
        add(f'<text x="{x+SW/2}" y="{y+SH/2+16}" text-anchor="middle" font-size="44" font-weight="bold" fill="{PALE}">{s}</text>')
x, y = xy("12")
add(f'<rect x="{x}" y="{y}" width="{SW}" height="{SH}" rx="6" fill="{BG}"/>')
add(f'<text x="{x+SW/2}" y="{y+SH/2+8}" text-anchor="middle" font-size="22" font-weight="bold" letter-spacing="2" fill="{LIGHT}">TRASH</text>')

heater_shaker("10")
tips("8", "300", "opentrons_96_tiprack_300ul")
tips("9", "20", "opentrons_96_tiprack_20ul")
reservoir("5")
reservoir("4", "Backup solvent reservoir", "same troughs, used when slot 5 runs low")
blank_plate("6")
for i, s in enumerate(["1", "2", "3"]):
    plate(s, i)

add('</svg>')
open(OUT, "w").write("\n".join(out))
print("ok", W, H)
