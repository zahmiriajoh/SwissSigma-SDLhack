"""Glue between the OT-2 protocol (sdl_solubility_ot2.py) and the (external) Bayesian optimization loop.

Runs on a laptop, not on the robot. Standard library only (Python 3.11+ for tomllib). Solvents, solutes, troughs,
volumes and the numbering convention come from ../production/config.toml (see ../production/README.md); rounds,
plates start at FIRST_ROUND / FIRST_PLATE (0); the DMF control is condition 0, mixtures count from FIRST_CONDITION (1).

Closed loop, one round = one well-level CSV run on up to 3 identical readout plates:

    grid    -> suggestions_round0.csv          (baseline design for the first round)
    BO      -> suggestions_roundN.csv          (frac_<solvent> columns, optional solute column)
    layout  -> ot_input_roundN.csv             (upload to sdl_solubility_ot2.py as the CSV parameter)
               plate_map_roundN.csv            (well -> solute / condition / role, used by merge)
    [OT-2 fills the plates, each is sealed + shaken, plate reader exports one file per plate]
    merge   -> results_roundN_wells.csv        (per well and plate)
               bo_dataset.csv                  (one row per solute x condition, all rounds)
               bo_dataset_shared.csv           (conditions run on every solute: min/mean objective)
    plate-svg -> picture of any plate map

Plate layout (all configurable, see SOLUTES in the config, CONTROLS_PER_SOLUTE / REPLICATES or the
layout flags): the plate is split into equal consecutive blocks of wells in row order,
one per solute. With 4 solutes that is 24 wells = 2 rows each. Each block starts with its
DMF controls, followed by the conditions (x replicate wells). Default: 1 DMF control +
23 conditions per solute.

Usage:
    python bo_bridge.py grid   --round 0 -o runs/suggestions_round0.csv
    python bo_bridge.py layout --round 0 --suggestions runs/suggestions_round0.csv --outdir runs/round0
    python bo_bridge.py merge  --plate-map runs/round0/plate_map_round0.csv \\
                               --reader runs/round0/plate0.csv runs/round0/plate1.csv runs/round0/plate2.csv \\
                               --dataset runs/bo_dataset.csv
"""

import argparse
import csv
import itertools
import math
import os
import random
import re
import statistics
import sys

# ---------------------------------------------------------------------------
# Experiment configuration: ../production/config.toml. sdl_solubility_ot2.py mirrors SOLVENT_TROUGHS by hand
# (the robot cannot import the repo); tests/test_interfaces.py checks the mirror.
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
from production.config import (  # noqa: E402
    ALL_SOLVENTS, FIRST_CONDITION, FIRST_PLATE, FIRST_ROUND, GREEN_SOLVENTS, LIMIT_SOLVENT_TO_TROUGH, MAX_SOLVENTS_PER_MIX,
    MIN_UL, N_PLATES, REFERENCE_SOLVENT, SOLUTES, SOLUTE_WAVELENGTH_NM, SOLVENT_TROUGHS, TOTAL_UL, TROUGH_USABLE_UL, is_allowed,
    sample_id,
)

CONTROLS_PER_SOLUTE = 1   # reference-solvent wells per solute per plate
REPLICATES = 1            # wells per condition per plate (plates are replicates too)

ROWS = "ABCDEFGH"
N_COLS = 12
PLATE_WELLS = [f"{r}{c}" for r in ROWS for c in range(1, N_COLS + 1)]  # row order
FRAC_COLS = [f"frac_{s}" for s in ALL_SOLVENTS]
VOL_COLS = [f"vol_{s}_ul" for s in ALL_SOLVENTS]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [row for row in csv.reader(f, dialect) if any(c.strip() for c in row)]


def read_dicts(path):
    rows = read_csv(path)
    return [dict(zip([h.strip() for h in rows[0]], [c.strip() for c in r])) for r in rows[1:]]


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def upsert_round(path, header, round_, new_rows):
    """Append rows to a cumulative CSV; re-merging a round replaces its rows."""
    existing = []
    if os.path.exists(path):
        old = read_csv(path)
        if old[0] != header:
            sys.exit(f"{path} has a different header (config changed?) - use a new dataset file")
        existing = [r for r in old[1:] if r[0] != str(round_)]
    write_csv(path, header, existing + new_rows)
    return len(existing) + len(new_rows)


def to_float(s):
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def fmt(x, nd=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"{x:.{nd}f}"


def mean_std(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None
    return statistics.mean(vals), (statistics.stdev(vals) if len(vals) > 1 else None)


def normalize_well(name):
    m = re.fullmatch(r"\s*([A-Ha-h])\s*0*([1-9]|1[0-2])\s*", name)
    return f"{m.group(1).upper()}{m.group(2)}" if m else None


def fractions_to_volumes(fracs, total_ul):
    """Fractions -> integer uL volumes summing to total_ul, each 0 or >= MIN_UL.

    Returns (volumes, warnings). The realised fractions (vol / total_ul) are what the
    BO dataset records, so BO always learns from what was actually dispensed.
    """
    warnings = []
    vols = {s: fracs.get(s, 0.0) * total_ul for s in ALL_SOLVENTS}
    for s, v in vols.items():
        if 0 < v < MIN_UL:
            snapped = 0.0 if v < MIN_UL / 2 else float(MIN_UL)
            warnings.append(f"{s} {v:.1f} uL snapped to {snapped:.0f} uL (pipette min {MIN_UL})")
            vols[s] = snapped
    vols = {s: float(round(v)) for s, v in vols.items()}
    # put the rounding residue on the largest component
    largest = max(vols, key=vols.get)
    vols[largest] += total_ul - sum(vols.values())
    return vols, warnings


def solute_blocks(solutes, controls, replicates):
    """Split the plate (row order) into one equal block per solute.

    Returns ({solute: [wells]}, conditions_per_solute)."""
    per = len(PLATE_WELLS) // len(solutes)
    n_cond = (per - controls) // replicates
    if n_cond < 1:
        sys.exit(f"{per} wells per solute leaves no room for conditions "
                 f"({controls} controls, {replicates} replicates)")
    return {s: PLATE_WELLS[i * per:(i + 1) * per] for i, s in enumerate(solutes)}, n_cond


def layout_args(p):
    p.add_argument("--solutes", default=",".join(SOLUTES), help="comma-separated solute names")
    p.add_argument("--controls-per-solute", type=int, default=CONTROLS_PER_SOLUTE)
    p.add_argument("--replicates", type=int, default=REPLICATES, help="wells per condition per plate")


# ---------------------------------------------------------------------------
# grid: baseline design for the first round
# ---------------------------------------------------------------------------

def pick_balanced(candidates, k):
    """Greedily pick k mixtures so every solvent is used about equally."""
    use = {s: 0 for s in GREEN_SOLVENTS}
    chosen, pool = [], list(candidates)
    for _ in range(min(k, len(pool))):
        best = min(pool, key=lambda d: sum(use[s] for s in d))  # stable: keeps shuffled order on ties
        pool.remove(best)
        chosen.append(best)
        for s in best:
            use[s] += 1
    return chosen


def cmd_grid(args):
    solutes = args.solutes.split(",")
    _, n_cond = solute_blocks(solutes, args.controls_per_solute, args.replicates)
    n = args.n or n_cond
    rng = random.Random(args.seed)
    designs = [{s: 1.0} for s in GREEN_SOLVENTS]  # pure solvents = single-solvent baselines
    binaries = [{a: 0.5, b: 0.5} for a, b in itertools.combinations(GREEN_SOLVENTS, 2) if is_allowed((a, b))]
    ternaries = [{a: 1 / 3, b: 1 / 3, c: 1 / 3} for a, b, c in itertools.combinations(GREEN_SOLVENTS, 3) if is_allowed((a, b, c))]
    rng.shuffle(binaries)
    rng.shuffle(ternaries)
    # mostly binaries, a few ternaries, so the round spans the simplex
    n_left = max(n - len(designs), 0)
    n_tern = n_left // 3
    chosen_bin = pick_balanced(binaries, n_left - n_tern)
    designs += chosen_bin + pick_balanced(ternaries, n_left - len(chosen_bin))
    designs = designs[:n]

    # no solute column: every condition is run on every solute (shared conditions)
    header = ["condition_id"] + [f"frac_{s}" for s in GREEN_SOLVENTS]
    rows = [
        [f"R{args.round}_grid{i + FIRST_CONDITION:02d}"] + [fmt(d.get(s, 0.0)) for s in GREEN_SOLVENTS]
        for i, d in enumerate(designs)
    ]
    write_csv(args.output, header, rows)
    print(f"wrote {len(rows)} baseline conditions (run on every solute) -> {args.output}")


# ---------------------------------------------------------------------------
# layout: suggestions -> robot CSV + plate map
# ---------------------------------------------------------------------------

def read_suggestions(path, solutes, round_):
    """Returns {solute: [(condition_id, fracs)]}. Rows without a solute go to every solute
    and keep one shared condition_id, so merge can score them across all solutes."""
    rows = read_csv(path)
    header = [c.strip() for c in rows[0]]
    unknown = [c for c in header if c.startswith("frac_") and c[5:] not in ALL_SOLVENTS]
    if unknown:
        sys.exit(f"Unknown solvent columns {unknown}; known: {ALL_SOLVENTS}")
    if not any(c.startswith("frac_") for c in header):
        sys.exit(f"{path}: expected frac_<solvent> columns, got {header}")
    out = {s: [] for s in solutes}
    counters = {}
    for i, row in enumerate(rows[1:], start=2):
        rec = dict(zip(header, [c.strip() for c in row]))
        fracs = {}
        for s in ALL_SOLVENTS:
            v = to_float(rec.get(f"frac_{s}", 0) or 0)
            if v is None or v < 0:
                sys.exit(f"{path} line {i}: bad frac_{s} '{rec.get(f'frac_{s}')}'")
            if v > 0:
                fracs[s] = v
        total = sum(fracs.values())
        if total <= 0:
            sys.exit(f"{path} line {i}: all fractions are zero")
        if abs(total - 1) > 0.02:
            print(f"  note: line {i} fractions sum to {total:.3f}, renormalising")
        fracs = {s: v / total for s, v in fracs.items()}
        if len(fracs) > MAX_SOLVENTS_PER_MIX:
            print(f"  warning: line {i} mixes {len(fracs)} solvents (> {MAX_SOLVENTS_PER_MIX})")
        if not is_allowed(fracs):
            sys.exit(f"{path} line {i}: {sorted(fracs)} contains a forbidden (immiscible) solvent pair, see production/config.toml")
        solute = rec.get("solute", "")
        if solute and solute not in out:
            sys.exit(f"{path} line {i}: unknown solute '{solute}'; known: {solutes}")
        key = solute or "shared"
        n = counters[key] = counters.get(key, FIRST_CONDITION - 1) + 1
        cond_id = rec.get("condition_id") or (f"R{round_}_{solute}_C{n:02d}" if solute else f"R{round_}_C{n:02d}")
        for s in ([solute] if solute else solutes):
            out[s].append((cond_id, fracs))
    return out


def cmd_layout(args):
    solutes = args.solutes.split(",")
    blocks, n_cond = solute_blocks(solutes, args.controls_per_solute, args.replicates)
    suggestions = read_suggestions(args.suggestions, solutes, args.round)
    for s, conds in suggestions.items():
        if len(conds) > n_cond:
            sys.exit(f"{s}: {len(conds)} conditions but only {n_cond} fit "
                     f"({len(blocks[s])} wells, {args.controls_per_solute} controls, "
                     f"{args.replicates} replicates)")

    ref_vols, _ = fractions_to_volumes({REFERENCE_SOLVENT: 1.0}, args.total_ul)
    ref_id = f"R{args.round}_{REFERENCE_SOLVENT}ref"
    wells = []  # (well, solute, condition_id, role, replicate, vols); replicates count from 0
    seen_ids = {}
    for s in solutes:
        block = blocks[s]
        for c in range(args.controls_per_solute):
            wells.append((block[c], s, ref_id, "control", c, ref_vols))
        conds = suggestions[s]
        for k, (cond_id, fracs) in enumerate(conds):
            vols, warnings = fractions_to_volumes(fracs, args.total_ul)
            if seen_ids.setdefault(cond_id, vols) != vols:
                sys.exit(f"condition_id {cond_id} used for two different mixtures")
            for w in warnings:
                print(f"  {s} {cond_id}: {w}")
            for r in range(args.replicates):
                # replicate r of condition k: replicate blocks follow each other
                idx = args.controls_per_solute + r * len(conds) + k
                wells.append((block[idx], s, cond_id, "sample", r, vols))
    wells.sort(key=lambda w: PLATE_WELLS.index(w[0]))
    # sample-id parts: solute number (config order) and the well's position in its block (0 = the DMF control)
    block_pos = {w: (SOLUTES.index(s) if s in SOLUTES else i, blocks[s].index(w))
                 for i, s in enumerate(solutes) for w in blocks[s]}

    tag = f"round{args.round}"
    ot_path = os.path.join(args.outdir, f"ot_input_{tag}.csv")
    map_path = os.path.join(args.outdir, f"plate_map_{tag}.csv")

    # robot CSV: only solvents that are actually used
    used = [s for s in ALL_SOLVENTS if any(w[5][s] > 0 for w in wells)]
    write_csv(
        ot_path,
        ["well", "solute", "condition_id"] + [f"vol_{s}_ul" for s in used],
        [[w, s, cid] + [f"{v[x]:g}" for x in used] for w, s, cid, _, _, v in wells],
    )
    write_csv(
        map_path,
        ["round", "well", "row", "col", "solute", "condition_id", "role", "replicate", "solute_index", "cond"]
        + FRAC_COLS + VOL_COLS,
        [[args.round, w, w[0], w[1:], s, cid, role, rep, *block_pos[w]]
         + [fmt(v[x] / args.total_ul) for x in ALL_SOLVENTS] + [f"{v[x]:g}" for x in ALL_SOLVENTS]
         for w, s, cid, role, rep, v in wells],
    )

    print(f"wrote {ot_path}\nwrote {map_path}\n")
    per = len(blocks[solutes[0]])
    print(f"Layout: {len(solutes)} solutes x {per} wells; per solute {args.controls_per_solute} DMF "
          f"control(s) + up to {n_cond} conditions x {args.replicates} replicate(s)")
    for s in solutes:
        b = blocks[s]
        print(f"  {s}: wells {b[0]}-{b[-1]}, {len(suggestions[s])} conditions")
    print(f"\nReservoir fill sheet ({args.plates} identical plates):")
    ok = True
    for x in used:
        need = args.plates * sum(w[5][x] for w in wells)
        have = TROUGH_USABLE_UL * len(SOLVENT_TROUGHS[x])
        flag = "" if need <= have else "  <-- TOO MUCH: add the spare trough in the protocol + here"
        ok &= need <= have
        print(f"  {x:<7} trough {','.join(SOLVENT_TROUGHS[x]):<6} needs {need / 1000:5.2f} mL{flag}")
    if not ok and LIMIT_SOLVENT_TO_TROUGH:
        sys.exit(1)
    if not ok:  # the BO is not limited to one trough (production/config.toml): the lab loads spare troughs instead
        print("\nWARNING: a solvent above needs more than one trough holds (limit_solvent_to_trough = false). Add spare troughs to "
              "SOLVENT_TROUGHS in the protocol and in production/config.toml, and load them, before running this round.")


# ---------------------------------------------------------------------------
# merge: plate reader exports + plate map -> BO dataset
# ---------------------------------------------------------------------------

def parse_reader(path, value_col=None, wavelength=None):
    """Returns {(well, wavelength_or_None): absorbance}.

    Accepts either a long table with a 'well' column (+ optional wavelength column), or one
    or more 8x12 grid blocks (row letter in the first cell, 12 numbers after it).
    """
    rows = read_csv(path)

    # long format
    for h_idx, row in enumerate(rows):
        lower = [c.strip().lower() for c in row]
        if "well" in lower:
            header = [c.strip() for c in row]
            w_idx = lower.index("well")
            wl_idx = next((i for i, c in enumerate(lower) if "wavelength" in c or c in ("nm", "lambda")), None)
            if value_col:
                if value_col not in header:
                    sys.exit(f"--value-col '{value_col}' not in reader header {header}")
                v_idx = header.index(value_col)
            else:
                body = rows[h_idx + 1:]
                v_idx = next(
                    (i for i in range(len(header)) if i not in (w_idx, wl_idx)
                     and body and all(to_float(r[i]) is not None for r in body if len(r) > i)),
                    None,
                )
                if v_idx is None:
                    sys.exit(f"Could not find a numeric absorbance column in {header}; pass --value-col")
            out = {}
            for r in rows[h_idx + 1:]:
                if len(r) <= max(w_idx, v_idx):
                    continue
                well = normalize_well(r[w_idx])
                val = to_float(r[v_idx])
                if well is None or val is None:
                    continue
                wl = to_float(r[wl_idx]) if wl_idx is not None and len(r) > wl_idx else None
                if wavelength is not None and wl is not None and abs(wl - wavelength) > 0.5:
                    continue
                out[(well, None if wavelength is not None else wl)] = val
            return out

    # grid format
    blocks, current = [], {}
    for row in rows:
        cells = [c.strip() for c in row]
        letter = cells[0].upper() if cells else ""
        nums = [to_float(c) for c in cells[1:13]]
        if letter in ROWS and len(letter) == 1 and len(nums) == 12 and all(n is not None for n in nums):
            current[letter] = nums
            if letter == "H":
                blocks.append(current)
                current = {}
    if not blocks:
        sys.exit(f"{path}: no 'well' column and no 8x12 grid found")
    if len(blocks) > 1:
        print(f"  note: {len(blocks)} grid blocks in {path}, using the first (one wavelength per file expected)")
    return {(f"{r}{c + 1}", None): v for r, vals in blocks[0].items() for c, v in enumerate(vals)}


def reader_lookup(readings):
    """Returns absorbance(well, solute) for one parsed reader file."""
    multi_wl = any(k[1] is not None for k in readings)

    def absorbance(well, solute):
        if not multi_wl:
            return readings.get((well, None))
        wl = SOLUTE_WAVELENGTH_NM.get(solute)
        if wl is None:
            sys.exit("Reader file has several wavelengths: pass --wavelength or set SOLUTE_WAVELENGTH_NM")
        return next((v for (w, l), v in readings.items() if w == well and abs(l - wl) <= 0.5), None)
    return absorbance


def well_sample_id(m, plate):
    """Sample id of plate-map row m on `plate`, e.g. round0_plate1_solute0_cond0 (needs layout's solute_index/cond)."""
    if "cond" not in m:
        sys.exit("plate map has no solute_index/cond columns: re-run bo_bridge.py layout to add sample ids")
    return sample_id(m["round"], plate, m["solute_index"], m["cond"])


def cmd_merge(args):
    plate_map = read_dicts(args.plate_map)
    round_ = plate_map[0]["round"]
    plates = [reader_lookup(parse_reader(p, args.value_col, args.wavelength)) for p in args.reader]
    blanks = [reader_lookup(parse_reader(p, args.value_col, args.wavelength)) for p in (args.blank or [])]

    # per well and plate: background-corrected absorbance
    obs = []  # (plate_no, map_row, raw, blank, corrected)
    for p_no, absorbance in enumerate(plates, start=FIRST_PLATE):
        for m in plate_map:
            raw = absorbance(m["well"], m["solute"])
            if raw is None:
                sys.exit(f"{args.reader[p_no - FIRST_PLATE]}: no reading for well {m['well']}")
            blank = statistics.mean(b(m["well"], m["solute"]) for b in blanks) if blanks else 0.0
            obs.append((p_no, m, raw, blank, raw - blank))

    # DMF reference per solute: mean of its control wells over all plates
    ref = {}
    for s in {m["solute"] for m in plate_map}:
        vals = [c for _, m, _, _, c in obs if m["solute"] == s and m["role"] == "control"]
        ref[s] = statistics.mean(vals) if vals else None
        if ref[s] is not None and ref[s] <= 0:
            print(f"  warning: DMF reference for {s} is {ref[s]:.4f} (<= 0) - relative values blank")
            ref[s] = None
        if not vals:
            print(f"  warning: no DMF control for {s} - rel_* left blank")

    def rel(m, c):
        return c / ref[m["solute"]] if ref[m["solute"]] else None

    wells_path = args.wells_out or os.path.join(
        os.path.dirname(os.path.abspath(args.plate_map)), f"results_round{round_}_wells.csv")
    write_csv(
        wells_path,
        ["round", "plate", "well", "sample_id", "solute", "condition_id", "role", "replicate",
         "abs_raw", "abs_blank", "abs_corrected", "rel_to_DMF"],
        [[round_, p, m["well"], well_sample_id(m, p), m["solute"], m["condition_id"], m["role"], m["replicate"],
          fmt(raw), fmt(blank), fmt(c), fmt(rel(m, c))] for p, m, raw, blank, c in obs],
    )

    # one row per solute x condition (all replicate wells x plates pooled)
    groups = {}
    for p, m, raw, blank, c in obs:
        groups.setdefault((m["solute"], m["condition_id"]), []).append((m, c))
    header = (["round", "solute", "condition_id", "is_reference", "n_solvents"] + FRAC_COLS
              + ["n_obs", "abs_mean", "abs_std", "rel_mean", "rel_std"])
    long_rows, rel_by = [], {}
    for (s, cid), items in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        m0 = items[0][0]
        fr = [to_float(m0[c]) for c in FRAC_COLS]
        a_mean, a_std = mean_std([c for _, c in items])
        r_mean, r_std = mean_std([rel(m, c) for m, c in items])
        rel_by[(s, cid)] = (r_mean, r_std, fr, m0["role"] == "control")
        long_rows.append(
            [round_, s, cid, int(m0["role"] == "control"), sum(1 for f in fr if f and f > 0)]
            + [fmt(f) for f in fr]
            + [len(items), fmt(a_mean), fmt(a_std), fmt(r_mean), fmt(r_std)]
        )
    n_long = upsert_round(args.dataset, header, round_, long_rows)

    # conditions run on every solute: one row with all solutes -> "dissolves everything" objective
    solutes = sorted({s for s, _ in groups})
    shared_ids = sorted({cid for _, cid in groups if all((s, cid) in groups for s in solutes)})
    shared_path = os.path.splitext(args.dataset)[0] + "_shared.csv"
    shared_header = (["round", "condition_id", "is_reference", "n_solvents"] + FRAC_COLS
                     + [f"rel_{s}_mean" for s in solutes] + ["obj_min_rel", "obj_mean_rel"])
    shared_rows = []
    for cid in shared_ids:
        rels = [rel_by[(s, cid)][0] for s in solutes]
        fr, is_ref = rel_by[(solutes[0], cid)][2], rel_by[(solutes[0], cid)][3]
        complete = all(r is not None for r in rels)
        shared_rows.append(
            [round_, cid, int(is_ref), sum(1 for f in fr if f and f > 0)] + [fmt(f) for f in fr]
            + [fmt(r) for r in rels]
            + [fmt(min(rels) if complete else None), fmt(statistics.mean(rels) if complete else None)]
        )
    n_shared = upsert_round(shared_path, shared_header, round_, shared_rows) if shared_rows else 0

    print(f"wrote {wells_path}")
    print(f"{args.dataset}: {n_long} solute x condition rows (all rounds)")
    if shared_rows:
        print(f"{shared_path}: {n_shared} shared conditions (all rounds)\n")
        print(f"{'condition':<18}" + "".join(f"{s:>9}" for s in solutes) + f"{'min':>8}")
        for r in shared_rows:
            vals = r[4 + len(FRAC_COLS): 4 + len(FRAC_COLS) + len(solutes)]
            print(f"{r[1]:<18}" + "".join(f"{v or '-':>9}" for v in vals) + f"{r[-2] or '-':>8}")


# ---------------------------------------------------------------------------
# plate-svg: picture of a plate map
# ---------------------------------------------------------------------------

# matplotlib "twilight" samples for solutes, "bone" for the neutral greys
SOLUTE_COLORS = ["#6d90c0", "#5f58b0", "#9f3c50", "#c0755e", "#a6bfca", "#531e7c", "#64194b", "#d0b39e"]
BONE_INK, BONE_DARK, BONE_MID, BONE_LIGHT, BONE_BG = "#16161e", "#42425d", "#707b90", "#b9d2d2", "#eff4f4"


def cmd_plate_svg(args):
    pm = read_dicts(args.plate_map)
    by_well = {m["well"]: m for m in pm}
    solutes = list(dict.fromkeys(m["solute"] for m in pm))
    color = {s: SOLUTE_COLORS[i % len(SOLUTE_COLORS)] for i, s in enumerate(solutes)}
    cond_no = {}
    for m in pm:  # number conditions per solute in plate order
        if m["role"] == "sample":
            cond_no.setdefault((m["solute"], m["condition_id"]), len(
                [k for k in cond_no if k[0] == m["solute"]]) + FIRST_CONDITION)
    cell, x0, y0 = 46, 56, 92
    W, H = x0 + 12 * cell + 30, y0 + 8 * cell + 150
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           'font-family="Arial">',
           f'<rect width="{W}" height="{H}" fill="#fff"/>',
           f'<text x="{x0}" y="32" font-size="19" font-weight="bold" fill="{BONE_INK}">Plate map: round {pm[0]["round"]}</text>',
           f'<text x="{x0}" y="54" font-size="12" fill="{BONE_MID}">Same layout on every identical plate. '
           f'Number = condition within that solute; replicate wells share a number.</text>',
           f'<rect x="{x0 - 8}" y="{y0 - 8}" width="{12 * cell + 16}" height="{8 * cell + 16}" rx="12" '
           f'fill="{BONE_BG}" stroke="{BONE_MID}"/>']
    for c in range(12):
        out.append(f'<text x="{x0 + c * cell + cell / 2}" y="{y0 - 16}" text-anchor="middle" font-size="12" fill="{BONE_MID}">{c + 1}</text>')
    for r, row in enumerate(ROWS):
        out.append(f'<text x="{x0 - 22}" y="{y0 + r * cell + cell / 2 + 4}" text-anchor="middle" font-size="12" fill="{BONE_MID}">{row}</text>')
        for c in range(12):
            cx, cy = x0 + c * cell + cell / 2, y0 + r * cell + cell / 2
            m = by_well.get(f"{row}{c + 1}")
            if m is None:
                out.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="#fff" stroke="{BONE_LIGHT}" stroke-dasharray="3 3"/>')
                continue
            col = color[m["solute"]]
            if m["role"] == "control":
                out.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="{BONE_DARK}" stroke="{col}" stroke-width="4"/>')
                out.append(f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="10" font-weight="bold" fill="#fff">DMF</text>')
            else:
                out.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="{col}" fill-opacity="0.3" stroke="{col}" stroke-width="2"/>')
                out.append(f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="12" font-weight="bold" fill="{BONE_INK}">'
                           f'{cond_no[(m["solute"], m["condition_id"])]}</text>')
    ly = y0 + 8 * cell + 40
    for i, sol in enumerate(solutes):
        wells = [m for m in pm if m["solute"] == sol]
        n_c = len({m["condition_id"] for m in wells if m["role"] == "sample"})
        n_ctrl = sum(m["role"] == "control" for m in wells)
        x = x0 + (i % 4) * 150
        y = ly + (i // 4) * 26
        out.append(f'<circle cx="{x + 8}" cy="{y - 4}" r="8" fill="{color[sol]}" fill-opacity="0.18" stroke="{color[sol]}" stroke-width="2"/>')
        out.append(f'<text x="{x + 22}" y="{y}" font-size="12" fill="{BONE_INK}">{sol}: {n_c} cond, {n_ctrl} DMF</text>')
    y = ly + ((len(solutes) - 1) // 4 + 1) * 26 + 14
    out.append(f'<circle cx="{x0 + 8}" cy="{y - 4}" r="8" fill="{BONE_DARK}"/>'
               f'<text x="{x0 + 22}" y="{y}" font-size="12" fill="{BONE_INK}">DMF-only control (reference = 1.0)</text>')
    out.append(f'<circle cx="{x0 + 288}" cy="{y - 4}" r="8" fill="#fff" stroke="{BONE_LIGHT}" stroke-dasharray="3 3"/>'
               f'<text x="{x0 + 302}" y="{y}" font-size="12" fill="{BONE_INK}">unused</text>')
    out.append("</svg>")
    with open(args.output, "w") as f:
        f.write("\n".join(out))
    print(f"wrote {args.output}")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("grid", help="baseline design (pure solvents + binary/ternary mixtures)")
    g.add_argument("--round", type=int, default=FIRST_ROUND)
    g.add_argument("--n", type=int, help="number of conditions (default: as many as fit per solute)")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("-o", "--output", required=True)
    layout_args(g)
    g.set_defaults(func=cmd_grid)

    lay = sub.add_parser("layout", help="suggestions CSV -> ot_input + plate_map")
    lay.add_argument("--round", type=int, required=True)
    lay.add_argument("--suggestions", required=True,
                     help="CSV with frac_<solvent> columns (+ optional condition_id, solute)")
    lay.add_argument("--outdir", required=True)
    lay.add_argument("--total-ul", type=float, default=TOTAL_UL, help="solvent volume per well")
    lay.add_argument("--plates", type=int, default=N_PLATES, help="identical plates (for the fill sheet)")
    layout_args(lay)
    lay.set_defaults(func=cmd_layout)

    m = sub.add_parser("merge", help="plate reader exports + plate_map -> bo_dataset.csv")
    m.add_argument("--plate-map", required=True)
    m.add_argument("--reader", required=True, nargs="+",
                   help="one plate reader export per plate (long 'well' table or 8x12 grid)")
    m.add_argument("--blank", nargs="*",
                   help="optional reader export(s) of the same layout without solids (solvent background)")
    m.add_argument("--dataset", required=True, help="cumulative BO dataset CSV (created/updated)")
    m.add_argument("--value-col", help="absorbance column name in a long-format export")
    m.add_argument("--wavelength", type=float, help="use only this wavelength from a multi-wavelength export")
    m.add_argument("--wells-out", help="per-well output path (default next to the plate map)")
    m.set_defaults(func=cmd_merge)

    sv = sub.add_parser("plate-svg", help="draw a plate map (which solute / condition sits in which well)")
    sv.add_argument("--plate-map", required=True)
    sv.add_argument("-o", "--output", required=True)
    sv.set_defaults(func=cmd_plate_svg)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
