"""Draws maps/plate_layout.svg from a bo_bridge plate map: solute blocks S0, S1, ... (config order) and, in every well,
its cond number from the sample id (round0_plate0_solute0_cond0; cond0 = the DMF control). Names: production/config.toml.

    python tools/draw_plate_map.py [plate_map.csv] [out.svg]
"""
import csv
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("production_config", HERE.parents[1] / "production" / "config.py")
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

PLATE_MAP = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "examples" / f"plate_map_round{cfg.FIRST_ROUND}.csv"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE.parent / "maps" / "plate_layout.svg"

# matplotlib "twilight" samples for solute blocks, "bone" for greys (same as the deck maps)
BLOCK_COLORS = ["#6d90c0", "#5f58b0", "#9f3c50", "#c0755e", "#a6bfca", "#531e7c", "#64194b", "#d0b39e"]
INK, DARK, MID, LIGHT, BG = "#16161e", "#42425d", "#707b90", "#b9d2d2", "#eff4f4"
ROWS, CELL, X0, Y0 = "ABCDEFGH", 46, 56, 92


def svg_text(x, y, text, size=12, fill=INK, anchor="start", bold=False):
    weight = ' font-weight="bold"' if bold else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}"{weight}>{text}</text>'


def main():
    pm = list(csv.DictReader(open(PLATE_MAP)))
    by_well = {m["well"]: m for m in pm}
    solutes = [s for s in cfg.SOLUTES if any(m["solute"] == s for m in pm)]
    tag = {s: f"S{i}" for i, s in enumerate(solutes)}
    color = {s: BLOCK_COLORS[i % len(BLOCK_COLORS)] for i, s in enumerate(solutes)}
    if "cond" not in pm[0]:
        sys.exit(f"{PLATE_MAP} has no cond column: re-run bo_bridge.py layout")
    cond = {m["well"]: int(m["cond"]) for m in pm}  # position in the solute block, as in the sample id

    plate_w, plate_h = 12 * CELL, 8 * CELL
    W, H = X0 + plate_w + 230, Y0 + plate_h + 90 + 22 * len(solutes)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Arial">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           svg_text(X0, 32, f"Plate map: round {pm[0]['round']}", 19, bold=True),
           svg_text(X0, 54, "Same layout on every identical plate. Number = cond in the sample id "
                            f"{cfg.sample_id('R', 'P', 'S', 'C')}.", 12, MID),
           f'<rect x="{X0 - 8}" y="{Y0 - 8}" width="{plate_w + 16}" height="{plate_h + 16}" rx="12" fill="{BG}" stroke="{MID}"/>']
    out += [svg_text(X0 + c * CELL + CELL / 2, Y0 - 16, c + 1, 12, MID, "middle") for c in range(12)]
    for r, row in enumerate(ROWS):
        out.append(svg_text(X0 - 22, Y0 + r * CELL + CELL / 2 + 4, row, 12, MID, "middle"))
        for c in range(12):
            cx, cy, m = X0 + c * CELL + CELL / 2, Y0 + r * CELL + CELL / 2, by_well.get(f"{row}{c + 1}")
            if m is None:
                out.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="#ffffff" stroke="{LIGHT}" stroke-dasharray="3 3"/>')
            elif m["role"] == "control":
                out.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="{DARK}" stroke="{color[m["solute"]]}" stroke-width="4"/>')
                out.append(svg_text(cx, cy + 4, cond[m["well"]], 12, "#ffffff", "middle", True))
            else:
                col = color[m["solute"]]
                out.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="{col}" fill-opacity="0.3" stroke="{col}" stroke-width="2"/>')
                out.append(svg_text(cx, cy + 4, cond[m["well"]], 12, INK, "middle", True))

    # block labels to the right of the plate: S0 Glutarimide, ... spanning that block's rows
    bx = X0 + plate_w + 20
    for s in solutes:
        rows = sorted({ROWS.index(m["well"][0]) for m in pm if m["solute"] == s})
        top, bottom = Y0 + rows[0] * CELL + 6, Y0 + (rows[-1] + 1) * CELL - 6
        out.append(f'<rect x="{bx}" y="{top}" width="5" height="{bottom - top}" rx="2" fill="{color[s]}"/>')
        mid = (top + bottom) / 2
        out.append(svg_text(bx + 14, mid - 2, tag[s], 15, color[s], bold=True))
        out.append(svg_text(bx + 14, mid + 15, s, 12))

    # legend: one line per solute, then the symbols
    ly = Y0 + plate_h + 44
    for i, s in enumerate(solutes):
        wells = [m for m in pm if m["solute"] == s]
        ctrl = ", ".join(str(cond[m["well"]]) for m in wells if m["role"] == "control")
        samples = [cond[m["well"]] for m in wells if m["role"] == "sample"]
        rows = sorted({m["well"][0] for m in wells})
        y = ly + i * 22
        out.append(f'<circle cx="{X0 + 8}" cy="{y - 4}" r="8" fill="{color[s]}" fill-opacity="0.3" stroke="{color[s]}" stroke-width="2"/>')
        out.append(svg_text(X0 + 24, y, f"<tspan font-weight=\"bold\">{tag[s]}</tspan>  {s} (solute{wells[0]['solute_index']}): "
                                         f"rows {rows[0]}–{rows[-1]}, cond {ctrl} = {cfg.REFERENCE_SOLVENT} control, "
                                         f"{min(samples)}–{max(samples)} = conditions"))
    y = ly + len(solutes) * 22 + 6
    out.append(f'<circle cx="{X0 + 8}" cy="{y - 4}" r="8" fill="{DARK}"/>')
    out.append(svg_text(X0 + 24, y, f"0 = {cfg.REFERENCE_SOLVENT}-only control (reference = 1.0)"))
    out.append(f'<circle cx="{X0 + 330}" cy="{y - 4}" r="8" fill="#ffffff" stroke="{LIGHT}" stroke-dasharray="3 3"/>')
    out.append(svg_text(X0 + 346, y, "unused"))
    out.append("</svg>")
    OUT.write_text("\n".join(out))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
