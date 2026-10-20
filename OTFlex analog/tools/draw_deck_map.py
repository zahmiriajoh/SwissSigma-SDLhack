"""Draws deck_map.svg for the Flex timing analog (sdl_solubility_flex_analog.py): the OT-2
deck layout mapped slot for slot onto the Flex grid. Static drawing: update the slot
assignments below if you move labware in the protocol, then re-run:

    python tools/draw_deck_map.py
"""
import importlib.util
import os
import sys
from pathlib import Path

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "deck_map.svg")
_spec = importlib.util.spec_from_file_location("production_config", Path(__file__).resolve().parents[2] / "production" / "config.py")
cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cfg)
# matplotlib "bone" (greys) + "twilight" (accents)
INK, DARK, MID, LIGHT, PALE, BG = "#16161e", "#42425d", "#707b90", "#b9d2d2", "#dde9e9", "#eff4f4"
TW = ["#e2d9e2", "#a6bfca", "#6d90c0", "#5f58b0", "#531e7c", "#64194b", "#9f3c50", "#c0755e", "#d0b39e"]
SW, SH, GAP = 190, 128, 10
X0, Y0 = 40, 96
GRID = [["A1", "A2", "A3", "A4"], ["B1", "B2", "B3", "B4"], ["C1", "C2", "C3", "C4"], ["D1", "D2", "D3", "D4"]]
OT2_SLOT = {"A1": "10", "A2": "11", "A3": "12", "B1": "7", "B2": "8", "B3": "9",
            "C1": "4", "C2": "5", "C3": "6", "D1": "1", "D2": "2", "D3": "3"}
out = []
add = out.append

def xy(slot):
    for r, row in enumerate(GRID):
        if slot in row:
            return X0 + row.index(slot) * (SW + GAP), Y0 + r * (SH + GAP)

def label(slot, text, sub):
    x, y = xy(slot)
    add(f'<text x="{x+SW/2}" y="{y+SH-20}" text-anchor="middle" font-size="12" font-weight="bold" fill="{INK}">{text}'
        f'<tspan font-weight="normal" fill="{MID}"> (OT-2: {OT2_SLOT[slot]})</tspan></text>')
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
    label(slot, f"Readout plate {n}", "sarstedt_96_wellplate_390ul_flat")

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
    label(slot, "Solvent blank plate", f"well X1 = trough X1, {cfg.TOTAL_UL} µL, no solids")


def tips(slot, size, rack):
    bx, by, w, h = frame(slot, PALE, MID)
    wells(bx, by, w, h, 2.6 if size == "50" else 3.1, "#ffffff", MID)
    label(slot, f"{size} µL tips", rack)

def reservoir(slot):
    bx, by, w, h = frame(slot, "#ffffff", DARK)
    # trough A1..H1 from production/config.toml; any trough without a solvent is the diluent
    by_trough = {t[0]: cfg.SOLVENT_LABELS[name] for name, t in cfg.SOLVENT_TROUGHS.items()}
    names = [by_trough.get(f"{r}1", "diluent") for r in "ABCDEFGH"]
    cols = [TW[2], TW[3], TW[4], TW[5], TW[6], TW[7], TW[8], LIGHT]
    bh = (h - 10) / 8
    for i in range(8):
        add(f'<rect x="{bx+6}" y="{by+5+i*bh:.1f}" width="{w-12}" height="{bh-1.6:.1f}" rx="2" fill="{cols[i]}" fill-opacity="0.85"/>')
        txt = "#ffffff" if 1 <= i <= 6 else INK
        add(f'<text x="{bx+w/2}" y="{by+5+i*bh+bh/2+2.8:.1f}" text-anchor="middle" font-size="7.5" fill="{txt}">{"ABCDEFGH"[i]}1 {names[i]}</text>')
    label(slot, "Solvent reservoir", "axygen_8_reservoir_30000ul")

def heater_shaker(slot):
    x, y = xy(slot)
    add(f'<rect x="{x+12}" y="{y+6}" width="{SW-24}" height="{SH-36}" rx="9" fill="{DARK}"/>')
    add(f'<rect x="{x+26}" y="{y+14}" width="{SW-52}" height="{SH-52}" rx="4" fill="{LIGHT}" stroke="{INK}"/>')
    add(f'<text x="{x+SW/2}" y="{y+SH/2-10}" text-anchor="middle" font-size="9.5" fill="{INK}">universal flat adapter</text>')
    add(f'<text x="{x+SW/2}" y="{y+SH/2+4}" text-anchor="middle" font-size="9" fill="{INK}">plates moved here by hand</text>')
    add(f'<text x="{x+SW/2}" y="{y+SH/2+17}" text-anchor="middle" font-size="9" fill="{INK}">(no gripper)</text>')
    label(slot, "Heater-shaker", "heaterShakerModuleV1")

W = X0 + 4 * (SW + GAP) + 20
H = Y0 + 4 * (SH + GAP) + 150
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Arial">')
add(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
add(f'<text x="{X0}" y="34" font-size="20" font-weight="bold" fill="{INK}">Flex deck map: OT-2 timing analog (sdl_solubility_flex_analog.py)</text>')
add(f'<text x="{X0}" y="56" font-size="12" fill="{MID}">P1000 single (left) = OT-2 P300 · P50 single (right) = OT-2 P20 · heater-shaker A1 · manual plate moves</text>')
for row in GRID:
    for s in row:
        x, y = xy(s)
        add(f'<rect x="{x}" y="{y}" width="{SW}" height="{SH}" rx="6" fill="{BG}" stroke="{PALE}" stroke-width="2"/>')
        add(f'<text x="{x+SW/2}" y="{y+SH/2+16}" text-anchor="middle" font-size="44" font-weight="bold" fill="{PALE}">{s}</text>')
# trash bin spans A3-A4
x, y = xy("A3")
add(f'<rect x="{x}" y="{y}" width="{2 * SW + GAP}" height="{SH}" rx="6" fill="{PALE}" stroke="{LIGHT}" stroke-width="2"/>')
add(f'<text x="{x+SW+GAP/2}" y="{y+SH/2+2}" text-anchor="middle" font-size="22" font-weight="bold" letter-spacing="2" fill="{MID}">TRASH</text>')
add(f'<text x="{x+SW+GAP/2}" y="{y+SH/2+22}" text-anchor="middle" font-size="10" fill="{MID}">trash bin A3–A4 (protocol: load_trash_bin("A3"))</text>')
add(f'<text x="{x+SW+GAP/2}" y="{y+SH/2+38}" text-anchor="middle" font-size="10" fill="{MID}">(OT-2: 12)</text>')
for s4 in ("B4", "C4", "D4"):
    x, y = xy(s4)
    add(f'<rect x="{x+1}" y="{y+1}" width="{SW-2}" height="{SH-2}" rx="6" fill="#ffffff" stroke="{PALE}" stroke-width="2" stroke-dasharray="6 4"/>')
    add(f'<text x="{x+SW/2}" y="{y+SH/2+16}" text-anchor="middle" font-size="44" font-weight="bold" fill="{PALE}">{s4}</text>')
    add(f'<text x="{x+SW/2}" y="{y+SH-14}" text-anchor="middle" font-size="9.5" fill="{MID}">not used</text>')

heater_shaker("A1")
tips("B2", "1000", "opentrons_flex_96_tiprack_1000ul")
tips("B3", "50", "opentrons_flex_96_tiprack_50ul")
reservoir("C2")
blank_plate("C3")
for i, s in enumerate(["D1", "D2", "D3"]):
    plate(s, i)


ly = Y0 + 4 * (SH + GAP) + 26
add(f'<text x="{X0}" y="{ly}" font-size="13.5" font-weight="bold" fill="{INK}">Run order</text>')
steps = [
    "1  Fill all plates in one pass, as on the OT-2 (P50 below 20 µL on 20 µL tips, P1000 from 20 µL on 300 µL)",
    "2  Pause: seal all plates by hand",
    "3  For plate 0, 1, 2: move onto the heater-shaker (prompted) → shake → back to its slot → read on UV-Vis",
]
for i, t in enumerate(steps):
    add(f'<text x="{X0}" y="{ly+24+i*20}" font-size="12" fill="{INK}">{t}</text>')
add(f'<text x="{X0}" y="{ly+24+3*20+8}" font-size="11" fill="{MID}">C3: blank plate, well X1 = trough X1. Free: A2, B1, C1. TIMER comments in the run log give fill/shake times.</text>')
add('</svg>')
open(OUT, "w").write("\n".join(out))
print("ok", W, H)
